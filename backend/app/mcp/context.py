"""MCPContextProvider — metadata-first MCP capability summary."""

from __future__ import annotations

from backend.app.mcp.manager import MCPManager, get_manager_for_workspace
from backend.app.mcp.models import MCPServerStatus
from backend.app.workspace.workspace import Workspace


class MCPContextProvider:
    """Inject short MCP server/tool inventory into Context (no result dumps)."""

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
        self._cached_text: str | None = None

    @property
    def manager(self) -> MCPManager:
        return self._manager

    def refresh(self) -> str:
        self._cached_text = self.build_workspace_context()
        return self._cached_text

    @property
    def cached(self) -> str | None:
        return self._cached_text

    def build_workspace_context(self) -> str:
        lines = ["## External MCP capabilities"]
        servers = self._manager.list_servers()
        if not servers:
            lines.append("(no MCP servers configured)")
            lines.append(
                "Tip: add workspace/.codewisp/mcp.json or ~/.codewisp/config.json"
            )
            return "\n".join(lines)

        for rt in servers:
            if not rt.config.enabled:
                mark = "✗ disabled"
            elif rt.status is MCPServerStatus.CONNECTED:
                mark = "✓ connected"
            elif rt.status is MCPServerStatus.ERROR:
                mark = f"⚠ error ({rt.message[:40]})" if rt.message else "⚠ error"
            else:
                mark = f"○ {rt.status.value}"
            lines.append("")
            lines.append(f"{rt.config.display_name}")
            lines.append(f"  {mark}")
            if rt.connected and rt.tools:
                for t in rt.tools[:20]:
                    desc = (t.description or "").strip()
                    if len(desc) > 60:
                        desc = desc[:59] + "…"
                    suffix = f" — {desc}" if desc else ""
                    lines.append(f"  - {t.tool_name}{suffix}")
                if len(rt.tools) > 20:
                    lines.append(f"  ... and {len(rt.tools) - 20} more tools")
            elif rt.config.enabled and not rt.connected:
                lines.append("  (connect via /mcp connect <server> or auto on run)")

        lines.append("")
        lines.append(
            "Tip: MCP tools appear as mcp.<server>.<tool> in the tool list; "
            "use them like built-in tools."
        )
        return "\n".join(lines)
