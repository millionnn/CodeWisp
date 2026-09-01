"""MCPService — high-level boundary for Agent / API / CLI (never expose raw client)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.mcp.errors import MCPError, MCPServerNotFoundError, MCPToolNotFoundError
from backend.app.mcp.manager import MCPManager, get_manager_for_workspace
from backend.app.mcp.models import MCPCallResult, MCPServerRuntime, MCPToolInfo
from backend.app.mcp.policy import MCPToolPolicy
from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.handler import PermissionHandler
from backend.app.permissions.request import PermissionRequest
from backend.app.workspace.workspace import Workspace


class MCPService:
    def __init__(
        self,
        workspace: Workspace | str,
        *,
        manager: MCPManager | None = None,
    ) -> None:
        if isinstance(workspace, str):
            self._workspace = Workspace(workspace)
        else:
            self._workspace = workspace
        self._manager = manager or get_manager_for_workspace(self._workspace.root)
        self._policy = MCPToolPolicy()

    @property
    def manager(self) -> MCPManager:
        return self._manager

    @property
    def workspace(self) -> Workspace:
        return self._workspace

    def reload(self) -> list[MCPServerRuntime]:
        self._manager.reload_config()
        return self._manager.connect_all_enabled()

    def list_servers(self) -> list[MCPServerRuntime]:
        return self._manager.list_servers()

    def get_server(self, server_id: str) -> MCPServerRuntime:
        return self._manager.get_server(server_id)

    def connect(self, server_id: str) -> MCPServerRuntime:
        return self._manager.connect(server_id)

    def disconnect(self, server_id: str) -> MCPServerRuntime:
        return self._manager.disconnect(server_id)

    def list_tools(self, server_id: str | None = None) -> list[MCPToolInfo]:
        if server_id:
            rt = self._manager.get_server(server_id)
            return list(rt.tools)
        return self._manager.list_all_tools()

    def call_tool(
        self,
        server_id: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        *,
        permission_handler: PermissionHandler | None = None,
        session_id: str | None = None,
        confirm: bool = False,
    ) -> MCPCallResult:
        """API/CLI test path — still goes through permission policy."""
        rt = self._manager.get_server(server_id)
        info = next((t for t in rt.tools if t.tool_name == tool_name), None)
        if info is None and rt.connected:
            # refresh
            try:
                client = self._manager.get_client(server_id)
                tools = client.list_tools()
                rt.tools = tools
                info = next((t for t in tools if t.tool_name == tool_name), None)
            except MCPError:
                pass
        if info is None:
            raise MCPToolNotFoundError(
                f"MCP tool not found: {server_id}.{tool_name}"
            )

        decision = self._policy.decide(
            tool_name,
            annotations=info.annotations,
            permission_level=info.permission_level,
        )
        if decision.action.value == "deny":
            return MCPCallResult(
                success=False,
                content="",
                error=decision.reason,
                metadata={"denied": True, "policy": "deny"},
            )
        if decision.action.value == "ask":
            if not confirm and permission_handler is None:
                return MCPCallResult(
                    success=False,
                    content="",
                    error="MCP tool requires confirm=true or PermissionHandler",
                    metadata={"permission_required": True},
                )
            if permission_handler is not None and not confirm:
                perm = PermissionRequest(
                    command=f"mcp:{server_id}",
                    args=(tool_name,),
                    reason=decision.reason,
                    tool_name=f"mcp.{server_id}.{tool_name}",
                    session_id=session_id,
                )
                user = permission_handler.request(perm)
                if user is PermissionDecision.DENY:
                    return MCPCallResult(
                        success=False,
                        content="",
                        error="User denied MCP tool permission.",
                        metadata={"denied": True},
                    )

        client = self._manager.get_client(server_id)
        return client.call_tool(tool_name, arguments or {})

    def render_servers(self) -> str:
        lines = ["MCP Servers", ""]
        servers = self.list_servers()
        if not servers:
            lines.append("(none configured)")
            return "\n".join(lines)
        for rt in servers:
            lines.append(rt.render_line())
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def render_tools(self) -> str:
        lines = ["MCP Tools", ""]
        servers = self.list_servers()
        if not servers:
            lines.append("(none configured)")
            return "\n".join(lines)
        for rt in servers:
            if not rt.config.enabled:
                status = "✗ disabled"
            elif rt.connected:
                status = "✓ connected"
            elif rt.status.value == "error":
                status = "⚠ unavailable"
            else:
                status = "○ disconnected"
            lines.append(f"{rt.config.display_name}  {status}")
            if rt.tools:
                for t in rt.tools:
                    lines.append(f"  {t.tool_name}")
            else:
                lines.append("  (no tools)")
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    @staticmethod
    def for_workspace_root(
        root: str | Path, *, manager: MCPManager | None = None
    ) -> MCPService:
        return MCPService(Workspace(root), manager=manager)
