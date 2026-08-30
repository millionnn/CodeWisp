"""ExecutionService：在 Workspace 边界内受控执行命令（无 shell）。"""

from __future__ import annotations

import subprocess
import threading
import time
from collections.abc import Callable
from typing import Any

from backend.app.execution.errors import InvalidExecutionRequestError
from backend.app.execution.request import ExecutionRequest
from backend.app.execution.result import ExecutionResult
from backend.app.workspace.errors import PathOutsideWorkspaceError, WorkspaceError
from backend.app.workspace.workspace import Workspace

DEFAULT_MAX_OUTPUT_CHARS = 50_000

LineCallback = Callable[[str, str], None]  # (stream, line)


class ExecutionService:
    """语言无关的命令执行器。

    - 不使用 shell=True
    - cwd 必须经 Workspace.resolve_path
    - 强制 timeout；截断过大 stdout/stderr
    - 可预期失败一律返回 ExecutionResult，不向外抛未捕获异常
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    ) -> None:
        if max_output_chars < 1:
            raise InvalidExecutionRequestError("max_output_chars 必须 >= 1")
        self._workspace = workspace
        self._max_output_chars = max_output_chars

    @property
    def workspace(self) -> Workspace:
        return self._workspace

    def run(
        self,
        request: ExecutionRequest,
        *,
        on_line: LineCallback | None = None,
    ) -> ExecutionResult:
        """执行请求并返回结构化结果。

        ``on_line(stream, line)``：可选，按行回调 stdout/stderr（不含换行符）。
        """
        started = time.perf_counter()
        try:
            request.validate()
        except InvalidExecutionRequestError as exc:
            return self._failure_result(
                request,
                error=str(exc),
                started=started,
                metadata={"error_type": "invalid_request"},
            )

        try:
            cwd_path = self._workspace.resolve_path(request.cwd)
        except PathOutsideWorkspaceError as exc:
            return self._failure_result(
                request,
                error=str(exc),
                started=started,
                metadata={"error_type": "cwd_outside_workspace"},
            )
        except WorkspaceError as exc:
            return self._failure_result(
                request,
                error=str(exc),
                started=started,
                metadata={"error_type": "cwd_resolve_error"},
            )

        if not cwd_path.exists():
            return self._failure_result(
                request,
                error=f"cwd 不存在：{request.cwd}",
                started=started,
                metadata={"error_type": "cwd_missing"},
            )
        if not cwd_path.is_dir():
            return self._failure_result(
                request,
                error=f"cwd 不是目录：{request.cwd}",
                started=started,
                metadata={"error_type": "cwd_not_directory"},
            )

        cwd_display = self._workspace.relative_to_root(cwd_path)
        argv = request.argv()
        env = dict(request.env) if request.env is not None else None

        if on_line is None:
            return self._run_buffered(
                request,
                argv=argv,
                cwd_path=cwd_path,
                cwd_display=cwd_display,
                env=env,
                started=started,
            )
        return self._run_streaming(
            request,
            argv=argv,
            cwd_path=cwd_path,
            cwd_display=cwd_display,
            env=env,
            started=started,
            on_line=on_line,
        )

    def _run_buffered(
        self,
        request: ExecutionRequest,
        *,
        argv: list[str],
        cwd_path: Any,
        cwd_display: str,
        env: dict[str, str] | None,
        started: float,
    ) -> ExecutionResult:
        try:
            completed = subprocess.run(  # noqa: S603
                argv,
                cwd=str(cwd_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=request.timeout,
                env=env,
                check=False,
            )
        except FileNotFoundError:
            return self._failure_result(
                request,
                error=f"命令不存在或无法执行：{request.command}",
                started=started,
                cwd=cwd_display,
                metadata={"error_type": "command_not_found"},
            )
        except subprocess.TimeoutExpired as exc:
            stdout, trunc_out = self._clip(_decode_captured(exc.stdout))
            stderr, trunc_err = self._clip(_decode_captured(exc.stderr))
            if not stderr:
                stderr = f"命令超时（>{request.timeout}s）。"
            return ExecutionResult(
                success=False,
                exit_code=None,
                stdout=stdout,
                stderr=stderr,
                duration_ms=self._elapsed_ms(started),
                command=request.command,
                args=list(request.args),
                cwd=cwd_display,
                timed_out=True,
                truncated=trunc_out or trunc_err,
                metadata={"error_type": "timeout", "timeout": request.timeout},
            )
        except OSError as exc:
            return self._failure_result(
                request,
                error=f"执行失败：{exc}",
                started=started,
                cwd=cwd_display,
                metadata={"error_type": "os_error"},
            )
        except Exception as exc:  # noqa: BLE001
            return self._failure_result(
                request,
                error=f"执行异常：{exc}",
                started=started,
                cwd=cwd_display,
                metadata={"error_type": "unexpected"},
            )

        stdout, trunc_out = self._clip(completed.stdout or "")
        stderr, trunc_err = self._clip(completed.stderr or "")
        exit_code = int(completed.returncode)
        return ExecutionResult(
            success=exit_code == 0,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=self._elapsed_ms(started),
            command=request.command,
            args=list(request.args),
            cwd=cwd_display,
            timed_out=False,
            truncated=trunc_out or trunc_err,
            metadata={},
        )

    def _run_streaming(
        self,
        request: ExecutionRequest,
        *,
        argv: list[str],
        cwd_path: Any,
        cwd_display: str,
        env: dict[str, str] | None,
        started: float,
        on_line: LineCallback,
    ) -> ExecutionResult:
        try:
            proc = subprocess.Popen(  # noqa: S603
                argv,
                cwd=str(cwd_path),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                encoding="utf-8",
                errors="replace",
                env=env,
            )
        except FileNotFoundError:
            return self._failure_result(
                request,
                error=f"命令不存在或无法执行：{request.command}",
                started=started,
                cwd=cwd_display,
                metadata={"error_type": "command_not_found"},
            )
        except OSError as exc:
            return self._failure_result(
                request,
                error=f"执行失败：{exc}",
                started=started,
                cwd=cwd_display,
                metadata={"error_type": "os_error"},
            )

        stdout_chunks: list[str] = []
        stderr_chunks: list[str] = []

        def _reader(stream: Any, name: str, bucket: list[str]) -> None:
            assert stream is not None
            for line in stream:
                bucket.append(line)
                on_line(name, line.rstrip("\n"))

        t_out = threading.Thread(
            target=_reader, args=(proc.stdout, "stdout", stdout_chunks), daemon=True
        )
        t_err = threading.Thread(
            target=_reader, args=(proc.stderr, "stderr", stderr_chunks), daemon=True
        )
        t_out.start()
        t_err.start()

        timed_out = False
        try:
            proc.wait(timeout=request.timeout)
        except subprocess.TimeoutExpired:
            timed_out = True
            proc.kill()
            try:
                proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                pass

        t_out.join(timeout=5)
        t_err.join(timeout=5)

        stdout, trunc_out = self._clip("".join(stdout_chunks))
        stderr, trunc_err = self._clip("".join(stderr_chunks))
        if timed_out and not stderr:
            stderr = f"命令超时（>{request.timeout}s）。"

        exit_code = None if timed_out else int(proc.returncode or 0)
        return ExecutionResult(
            success=(not timed_out) and exit_code == 0,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=self._elapsed_ms(started),
            command=request.command,
            args=list(request.args),
            cwd=cwd_display,
            timed_out=timed_out,
            truncated=trunc_out or trunc_err,
            metadata={"error_type": "timeout", "timeout": request.timeout}
            if timed_out
            else {},
        )

    def _clip(self, text: str) -> tuple[str, bool]:
        limit = self._max_output_chars
        if len(text) <= limit:
            return text, False
        return text[:limit] + "\n...[truncated]...", True

    def _failure_result(
        self,
        request: ExecutionRequest,
        *,
        error: str,
        started: float,
        cwd: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        return ExecutionResult(
            success=False,
            exit_code=None,
            stdout="",
            stderr=error,
            duration_ms=self._elapsed_ms(started),
            command=request.command,
            args=list(request.args),
            cwd=cwd if cwd is not None else request.cwd,
            timed_out=False,
            truncated=False,
            metadata=metadata or {},
        )

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 3)


def _decode_captured(raw: str | bytes | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return raw
