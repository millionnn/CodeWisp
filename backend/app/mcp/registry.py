"""Sync discovered MCP tools into ToolRegistry."""

from __future__ import annotations

from typing import Callable

from backend.app.mcp.adapter import MCPToolAdapter
from backend.app.mcp.manager import MCPManager
from backend.app.mcp.models import MCPServerStatus
from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.handler import PermissionHandler
from backend.app.permissions.request import PermissionRequest
from backend.app.tools.registry import ToolRegistry


def mcp_tool_id_prefix(server_id: str) -> str:
    return f"mcp.{server_id}."


def unregister_mcp_tools(registry: ToolRegistry, *, server_id: str | None = None) -> int:
    """Remove MCP tools from registry. If server_id given, only that server."""
    removed = 0
    for tool in list(registry.list_tools()):
        name = tool.name
        if not name.startswith("mcp."):
            continue
        if server_id is not None and not name.startswith(mcp_tool_id_prefix(server_id)):
            continue
        if registry.unregister(name):
            removed += 1
    return removed


def sync_mcp_tools_to_registry(
    registry: ToolRegistry,
    manager: MCPManager,
    *,
    permission_handler: PermissionHandler | None = None,
    session_id: str | None = None,
    agent_run_id: str | None = None,
    on_permission_wait: Callable[[PermissionRequest], None] | None = None,
    on_permission_resolved: Callable[
        [PermissionRequest, PermissionDecision | None], None
    ]
    | None = None,
    connect_enabled: bool = False,
) -> list[str]:
    """Register/replace MCP adapters for connected servers.

    Returns list of registered tool ids. Does not raise on per-server failure.
    """
    if connect_enabled:
        manager.connect_all_enabled()

    unregister_mcp_tools(registry)
    registered: list[str] = []
    for runtime in manager.list_servers():
        if runtime.status is not MCPServerStatus.CONNECTED:
            continue
        try:
            client = manager.get_client(runtime.server_id)
        except Exception:  # noqa: BLE001
            continue
        for info in runtime.tools:
            if not info.enabled:
                continue
            adapter = MCPToolAdapter(
                info,
                client,
                permission_handler=permission_handler,
                session_id=session_id,
                agent_run_id=agent_run_id,
                on_permission_wait=on_permission_wait,
                on_permission_resolved=on_permission_resolved,
            )
            # Collision with built-in: mcp.* prefix avoids overlap; still replace safely
            if registry.contains(adapter.name) and not adapter.name.startswith("mcp."):
                continue
            registry.register_or_replace(adapter)
            registered.append(adapter.name)
    return registered
