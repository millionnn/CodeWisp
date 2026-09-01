"""MCPToolAdapter — MCP tool → CodeWisp Tool (AgentLoop sees a normal Tool)."""

from __future__ import annotations

from typing import Any, Callable

from backend.app.mcp.client import MCPClient
from backend.app.mcp.errors import MCPError
from backend.app.mcp.models import MCPPermissionLevel, MCPToolInfo
from backend.app.mcp.policy import MCPPolicyAction, MCPToolPolicy
from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.handler import PermissionHandler
from backend.app.permissions.request import PermissionRequest
from backend.app.tools.base import Tool
from backend.app.tools.result import ToolResult


class MCPToolAdapter(Tool):
    """Wraps one MCP tool as a first-class CodeWisp Tool."""

    def __init__(
        self,
        info: MCPToolInfo,
        client: MCPClient,
        *,
        permission_handler: PermissionHandler | None = None,
        session_id: str | None = None,
        agent_run_id: str | None = None,
        on_permission_wait: Callable[[PermissionRequest], None] | None = None,
        on_permission_resolved: Callable[
            [PermissionRequest, PermissionDecision | None], None
        ]
        | None = None,
        policy: MCPToolPolicy | None = None,
        display_name: str | None = None,
    ) -> None:
        self._info = info
        self._client = client
        self._permission_handler = permission_handler
        self._session_id = session_id
        self._agent_run_id = agent_run_id
        self._on_permission_wait = on_permission_wait
        self._on_permission_resolved = on_permission_resolved
        self._policy = policy or MCPToolPolicy()
        self._display_name = display_name

    @property
    def info(self) -> MCPToolInfo:
        return self._info

    @property
    def name(self) -> str:
        # Unique registry id; LLM schemas use this name.
        return self._info.tool_id

    @property
    def description(self) -> str:
        base = self._info.description or f"MCP tool {self._info.tool_name}"
        return (
            f"[MCP:{self._info.server_id}] {base} "
            f"(permission={self._info.permission_level.value})"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        schema = dict(self._info.input_schema or {})
        if schema.get("type") != "object":
            schema = {"type": "object", "properties": schema.get("properties") or {}}
        if "properties" not in schema:
            schema["properties"] = {}
        return schema

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        args = dict(arguments or {})
        decision = self._policy.decide(
            self._info.tool_name,
            annotations=self._info.annotations,
            permission_level=self._info.permission_level,
        )

        meta_base = {
            "server_id": self._info.server_id,
            "tool_name": self._info.tool_name,
            "mcp_tool_id": self._info.tool_id,
            "permission_level": decision.permission_level.value,
            "display": self._display_name
            or f"MCP · {self._info.server_id}.{self._info.tool_name}",
        }

        if decision.action is MCPPolicyAction.DENY:
            return ToolResult(
                success=False,
                output=None,
                error=decision.reason,
                metadata={**meta_base, "denied": True, "policy": "deny"},
            )

        if decision.action is MCPPolicyAction.ASK:
            if self._permission_handler is None:
                return ToolResult(
                    success=False,
                    output=None,
                    error=(
                        "MCP tool requires permission but no PermissionHandler "
                        "is configured."
                    ),
                    metadata={
                        **meta_base,
                        "permission_required": True,
                        "denied": True,
                    },
                )
            preview_args = _short_args(args)
            perm = PermissionRequest(
                command=f"mcp:{self._info.server_id}",
                args=(self._info.tool_name, preview_args),
                cwd=".",
                reason=(
                    f"MCP {self._info.server_id}.{self._info.tool_name}\n"
                    f"Permission required\n\n"
                    f"Server: {self._info.server_id}\n"
                    f"Tool: {self._info.tool_name}\n"
                    f"Args: {preview_args}"
                ),
                tool_name=self.name,
                session_id=self._session_id,
                agent_run_id=self._agent_run_id,
            )
            if self._on_permission_wait is not None:
                try:
                    self._on_permission_wait(perm)
                except Exception:  # noqa: BLE001
                    pass
            user_decision: PermissionDecision | None = None
            try:
                user_decision = self._permission_handler.request(perm)
            finally:
                if self._on_permission_resolved is not None:
                    try:
                        self._on_permission_resolved(perm, user_decision)
                    except Exception:  # noqa: BLE001
                        pass
            if user_decision is PermissionDecision.DENY or user_decision is None:
                return ToolResult(
                    success=False,
                    output=None,
                    error="User denied MCP tool permission.",
                    metadata={
                        **meta_base,
                        "permission_required": True,
                        "denied": True,
                        "decision": (
                            user_decision.value if user_decision else "interrupted"
                        ),
                    },
                )

        if not self._client.connected:
            return ToolResult(
                success=False,
                output=None,
                error=f"MCP server '{self._info.server_id}' is unavailable.",
                metadata={**meta_base, "unavailable": True},
            )

        try:
            result = self._client.call_tool(self._info.tool_name, args)
        except MCPError as exc:
            return ToolResult(
                success=False,
                output=None,
                error=str(exc),
                metadata={
                    **meta_base,
                    "error_code": getattr(exc, "code", "MCP_ERROR"),
                },
            )
        except Exception as exc:  # noqa: BLE001 — never crash Agent
            return ToolResult(
                success=False,
                output=None,
                error=f"MCP call failed: {exc}",
                metadata={**meta_base, "error_code": "MCP_TOOL_CALL_FAILED"},
            )

        meta = {**meta_base, **(result.metadata or {})}
        if not result.success:
            return ToolResult(
                success=False,
                output=result.content or None,
                error=result.error or "MCP tool failed",
                metadata=meta,
            )
        return ToolResult(
            success=True,
            output=result.content,
            error=None,
            metadata=meta,
        )


def _short_args(args: dict[str, Any], limit: int = 120) -> str:
    text = str(args)
    text = text.replace("\n", " ")
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text
