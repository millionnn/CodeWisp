"""MCP stdio transport — Content-Length framed JSON-RPC 2.0 (LSP-style)."""

from __future__ import annotations

import json
import os
import subprocess
import threading
from typing import Any, BinaryIO

from backend.app.mcp.errors import MCPConnectionFailedError, MCPProtocolError, MCPTimeoutError


class StdioJSONRPCTransport:
    """Synchronous JSON-RPC over child process stdio (binary framed)."""

    def __init__(
        self,
        *,
        command: str,
        args: tuple[str, ...] = (),
        env: dict[str, str] | None = None,
        cwd: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._command = command
        self._args = args
        self._env = env
        self._cwd = cwd
        self._timeout = timeout
        self._proc: subprocess.Popen[bytes] | None = None
        self._id = 0
        self._lock = threading.Lock()
        self._pending: dict[int, dict[str, Any]] = {}
        self._reader: threading.Thread | None = None
        self._closed = False

    @property
    def alive(self) -> bool:
        return self._proc is not None and self._proc.poll() is None

    def start(self) -> None:
        if self.alive:
            return
        env = os.environ.copy()
        if self._env:
            env.update(self._env)
        try:
            self._proc = subprocess.Popen(
                [self._command, *self._args],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                cwd=self._cwd,
                env=env,
            )
        except OSError as exc:
            raise MCPConnectionFailedError(f"Failed to start MCP server: {exc}") from exc
        self._closed = False
        self._reader = threading.Thread(target=self._read_loop, daemon=True)
        self._reader.start()

    def close(self) -> None:
        self._closed = True
        proc = self._proc
        self._proc = None
        if proc is None:
            return
        try:
            if proc.stdin:
                proc.stdin.close()
        except Exception:  # noqa: BLE001
            pass
        try:
            proc.terminate()
            proc.wait(timeout=2)
        except Exception:  # noqa: BLE001
            try:
                proc.kill()
            except Exception:  # noqa: BLE001
                pass

    def request(self, method: str, params: dict[str, Any] | None = None) -> Any:
        with self._lock:
            if not self.alive or self._proc is None or self._proc.stdin is None:
                raise MCPConnectionFailedError("MCP transport is not connected")
            self._id += 1
            req_id = self._id
            msg: dict[str, Any] = {
                "jsonrpc": "2.0",
                "id": req_id,
                "method": method,
            }
            if params is not None:
                msg["params"] = params
            event = threading.Event()
            slot: dict[str, Any] = {"event": event, "result": None, "error": None}
            self._pending[req_id] = slot
            self._write(self._proc.stdin, msg)

        if not event.wait(self._timeout):
            with self._lock:
                self._pending.pop(req_id, None)
            raise MCPTimeoutError(f"MCP request timed out: {method}")

        if slot["error"] is not None:
            err = slot["error"]
            if isinstance(err, dict):
                raise MCPProtocolError(str(err.get("message") or err))
            raise MCPProtocolError(str(err))
        return slot["result"]

    def notify(self, method: str, params: dict[str, Any] | None = None) -> None:
        with self._lock:
            if not self.alive or self._proc is None or self._proc.stdin is None:
                raise MCPConnectionFailedError("MCP transport is not connected")
            msg: dict[str, Any] = {"jsonrpc": "2.0", "method": method}
            if params is not None:
                msg["params"] = params
            self._write(self._proc.stdin, msg)

    def _write(self, stdin: BinaryIO, msg: dict[str, Any]) -> None:
        body = json.dumps(msg, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
        try:
            stdin.write(header + body)
            stdin.flush()
        except OSError as exc:
            raise MCPConnectionFailedError(f"MCP write failed: {exc}") from exc

    def _read_loop(self) -> None:
        proc = self._proc
        if proc is None or proc.stdout is None:
            return
        try:
            while not self._closed and proc.poll() is None:
                msg = self._read_message(proc.stdout)
                if msg is None:
                    break
                if "id" in msg and ("result" in msg or "error" in msg):
                    req_id = msg.get("id")
                    with self._lock:
                        slot = self._pending.pop(req_id, None)
                    if slot is None:
                        continue
                    if "error" in msg:
                        slot["error"] = msg["error"]
                    else:
                        slot["result"] = msg.get("result")
                    slot["event"].set()
        except Exception:  # noqa: BLE001
            pass
        finally:
            with self._lock:
                for slot in self._pending.values():
                    slot["error"] = {"message": "MCP connection closed"}
                    slot["event"].set()
                self._pending.clear()

    def _read_message(self, stdout: BinaryIO) -> dict[str, Any] | None:
        headers: dict[str, str] = {}
        while True:
            line = stdout.readline()
            if line == b"":
                return None
            if line in (b"\r\n", b"\n"):
                break
            try:
                text = line.decode("ascii", errors="replace").rstrip("\r\n")
            except Exception:  # noqa: BLE001
                text = ""
            if ":" in text:
                k, v = text.split(":", 1)
                headers[k.strip().lower()] = v.strip()
        length_s = headers.get("content-length")
        if not length_s:
            raise MCPProtocolError("Missing Content-Length header")
        length = int(length_s)
        body = stdout.read(length)
        if len(body) < length:
            return None
        try:
            data = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise MCPProtocolError(f"Invalid JSON body: {exc}") from exc
        if not isinstance(data, dict):
            raise MCPProtocolError("JSON-RPC message must be an object")
        return data
