"""MCP client protocol + stdio / fake implementations."""

from __future__ import annotations

import uuid
from typing import Any, Protocol, runtime_checkable

from backend.app.mcp.errors import (
    MCPConnectionFailedError,
    MCPInitializationFailedError,
    MCPToolCallFailedError,
    MCPToolNotFoundError,
)
from backend.app.mcp.models import MCPCallResult, MCPServerConfig, MCPToolInfo
from backend.app.mcp.policy import classify_mcp_tool
from backend.app.mcp.transport import StdioJSONRPCTransport


@runtime_checkable
class MCPClient(Protocol):
    """Sync facade — AgentLoop / tools stay synchronous."""

    @property
    def server_id(self) -> str: ...

    @property
    def connected(self) -> bool: ...

    def connect(self) -> None: ...

    def disconnect(self) -> None: ...

    def list_tools(self) -> list[MCPToolInfo]: ...

    def call_tool(self, tool_name: str, arguments: dict[str, Any] | None = None) -> MCPCallResult: ...


class StdioMCPClient:
    """Local stdio MCP client (initialize + tools/list + tools/call)."""

    def __init__(
        self,
        config: MCPServerConfig,
        *,
        timeout: float = 30.0,
        workspace_root: str | None = None,
    ) -> None:
        self._config = config
        self._timeout = timeout
        self._workspace_root = workspace_root
        self._transport: StdioJSONRPCTransport | None = None
        self._tools: list[MCPToolInfo] = []
        self._protocol_version: str | None = None
        self._initialized = False

    @property
    def server_id(self) -> str:
        return self._config.server_id

    @property
    def connected(self) -> bool:
        return (
            self._initialized
            and self._transport is not None
            and self._transport.alive
        )

    @property
    def protocol_version(self) -> str | None:
        return self._protocol_version

    @property
    def cached_tools(self) -> list[MCPToolInfo]:
        return list(self._tools)

    def connect(self) -> None:
        if self.connected:
            return
        if not self._config.enabled:
            raise MCPConnectionFailedError(
                f"MCP server '{self.server_id}' is disabled"
            )
        merged_env = dict(self._config.env)
        if self._workspace_root:
            merged_env.setdefault("CODEWISP_WORKSPACE", self._workspace_root)
        transport = StdioJSONRPCTransport(
            command=self._config.command,
            args=self._config.args,
            env=merged_env,
            cwd=self._config.cwd or self._workspace_root,
            timeout=self._timeout,
        )
        try:
            transport.start()
            result = transport.request(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "codewisp", "version": "1.3"},
                },
            )
            if isinstance(result, dict):
                self._protocol_version = str(
                    result.get("protocolVersion") or "2024-11-05"
                )
            transport.notify("notifications/initialized", {})
            self._transport = transport
            self._initialized = True
            self._tools = self.list_tools()
        except Exception as exc:
            transport.close()
            self._transport = None
            self._initialized = False
            raise MCPInitializationFailedError(
                f"MCP initialize failed for '{self.server_id}': {exc}"
            ) from exc

    def disconnect(self) -> None:
        self._initialized = False
        self._tools = []
        if self._transport is not None:
            try:
                self._transport.notify("notifications/cancelled", {})
            except Exception:  # noqa: BLE001
                pass
            self._transport.close()
            self._transport = None

    def list_tools(self) -> list[MCPToolInfo]:
        if self._transport is None or not self._initialized:
            raise MCPConnectionFailedError(
                f"MCP server '{self.server_id}' is not connected"
            )
        result = self._transport.request("tools/list", {})
        tools_raw = []
        if isinstance(result, dict):
            tools_raw = result.get("tools") or []
        out: list[MCPToolInfo] = []
        for item in tools_raw:
            if not isinstance(item, dict):
                continue
            name = str(item.get("name") or "").strip()
            if not name:
                continue
            schema = item.get("inputSchema") or item.get("input_schema") or {
                "type": "object",
                "properties": {},
            }
            if not isinstance(schema, dict):
                schema = {"type": "object", "properties": {}}
            annotations = item.get("annotations") or {}
            if not isinstance(annotations, dict):
                annotations = {}
            level = classify_mcp_tool(name, annotations=annotations)
            out.append(
                MCPToolInfo(
                    server_id=self.server_id,
                    tool_name=name,
                    description=str(item.get("description") or ""),
                    input_schema=dict(schema),
                    permission_level=level,
                    annotations=dict(annotations),
                )
            )
        self._tools = out
        return list(out)

    def call_tool(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> MCPCallResult:
        if self._transport is None or not self._initialized:
            raise MCPConnectionFailedError(
                f"MCP server '{self.server_id}' is not connected"
            )
        name = (tool_name or "").strip()
        known = {t.tool_name for t in self._tools}
        if known and name not in known:
            # Refresh once in case tools changed
            try:
                self.list_tools()
                known = {t.tool_name for t in self._tools}
            except Exception:  # noqa: BLE001
                pass
            if known and name not in known:
                raise MCPToolNotFoundError(
                    f"MCP tool not found: {self.server_id}.{name}"
                )

        request_id = f"mcp_req_{uuid.uuid4().hex[:12]}"
        try:
            result = self._transport.request(
                "tools/call",
                {"name": name, "arguments": arguments or {}},
            )
        except Exception as exc:
            raise MCPToolCallFailedError(
                f"MCP tools/call failed ({self.server_id}.{name}): {exc}"
            ) from exc

        content_text, is_error = _extract_call_content(result)
        meta = {
            "server_id": self.server_id,
            "tool_name": name,
            "mcp_request_id": request_id,
        }
        if is_error:
            return MCPCallResult(
                success=False,
                content=content_text,
                error=content_text or "MCP tool reported error",
                metadata=meta,
            )
        return MCPCallResult(
            success=True,
            content=content_text,
            error=None,
            metadata=meta,
        )


class FakeMCPClient:
    """In-process fake for unit tests (no subprocess)."""

    def __init__(
        self,
        server_id: str,
        tools: list[MCPToolInfo] | None = None,
        *,
        call_handler: Any | None = None,
        fail_connect: bool = False,
    ) -> None:
        self._server_id = server_id
        self._tools = list(tools or [])
        self._call_handler = call_handler
        self._fail_connect = fail_connect
        self._connected = False
        self._calls: list[tuple[str, dict[str, Any]]] = []

    @property
    def server_id(self) -> str:
        return self._server_id

    @property
    def connected(self) -> bool:
        return self._connected

    def connect(self) -> None:
        if self._fail_connect:
            raise MCPInitializationFailedError(
                f"Fake MCP connect failed: {self._server_id}"
            )
        self._connected = True

    def disconnect(self) -> None:
        self._connected = False

    def list_tools(self) -> list[MCPToolInfo]:
        if not self._connected:
            raise MCPConnectionFailedError("Fake MCP not connected")
        return list(self._tools)

    def call_tool(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> MCPCallResult:
        if not self._connected:
            raise MCPConnectionFailedError("Fake MCP not connected")
        args = dict(arguments or {})
        self._calls.append((tool_name, args))
        known = {t.tool_name for t in self._tools}
        if tool_name not in known:
            raise MCPToolNotFoundError(f"Fake tool missing: {tool_name}")
        request_id = f"mcp_req_fake_{uuid.uuid4().hex[:8]}"
        meta = {
            "server_id": self._server_id,
            "tool_name": tool_name,
            "mcp_request_id": request_id,
        }
        if self._call_handler is not None:
            out = self._call_handler(tool_name, args)
            if isinstance(out, MCPCallResult):
                out.metadata.update(meta)
                return out
            return MCPCallResult(
                success=True, content=str(out), metadata=meta
            )
        return MCPCallResult(
            success=True,
            content=f"fake:{tool_name}:{args}",
            metadata=meta,
        )


def _extract_call_content(result: Any) -> tuple[str, bool]:
    if result is None:
        return "", False
    if isinstance(result, str):
        return result, False
    if not isinstance(result, dict):
        return str(result), False
    is_error = bool(result.get("isError"))
    content = result.get("content")
    if isinstance(content, str):
        return content, is_error
    if isinstance(content, list):
        parts: list[str] = []
        for block in content:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(str(block.get("text") or ""))
                else:
                    parts.append(str(block.get("text") or block))
            else:
                parts.append(str(block))
        return "\n".join(p for p in parts if p).strip(), is_error
    if "error" in result:
        return str(result.get("error")), True
    return str(result), is_error
