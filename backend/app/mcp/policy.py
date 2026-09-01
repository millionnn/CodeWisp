"""MCP tool permission classification — feeds existing PermissionHandler."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any

from backend.app.mcp.models import MCPPermissionLevel


class MCPPolicyAction(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True)
class MCPPolicyDecision:
    action: MCPPolicyAction
    reason: str
    permission_level: MCPPermissionLevel

    def to_dict(self) -> dict[str, str]:
        return {
            "action": self.action.value,
            "reason": self.reason,
            "permission_level": self.permission_level.value,
        }


_DANGEROUS_TOKENS = frozenset(
    {
        "shell",
        "exec",
        "execute",
        "bash",
        "cmd",
        "powershell",
        "sudo",
        "rm",
        "rmdir",
        "unlink",
        "drop",
        "truncate",
        "format",
        "destroy",
        "kill",
        "chmod",
        "chown",
        "eval",
    }
)

_WRITE_TOKENS = frozenset(
    {
        "write",
        "create",
        "update",
        "delete",
        "remove",
        "edit",
        "put",
        "post",
        "patch",
        "insert",
        "append",
        "upload",
        "send",
        "publish",
        "commit",
        "push",
        "apply",
        "mutate",
        "set_",
        "add_",
    }
)

_READ_TOKENS = frozenset(
    {
        "read",
        "get",
        "list",
        "search",
        "find",
        "query",
        "fetch",
        "show",
        "describe",
        "info",
        "status",
        "lookup",
        "inspect",
        "view",
        "stat",
        "head",
        "cat",
        "grep",
    }
)


def classify_mcp_tool(
    tool_name: str,
    *,
    annotations: dict[str, Any] | None = None,
) -> MCPPermissionLevel:
    """Heuristic + MCP annotations → ALLOW / ASK / DENY."""
    annotations = annotations or {}
    name = (tool_name or "").strip().lower()

    if annotations.get("destructiveHint") is True:
        return MCPPermissionLevel.DENY
    if annotations.get("readOnlyHint") is True:
        return MCPPermissionLevel.ALLOW
    if annotations.get("openWorldHint") is True and annotations.get("readOnlyHint") is not True:
        # Open-world write-ish tools need confirmation
        return MCPPermissionLevel.ASK

    tokens = set(name.replace("-", "_").split("_"))
    tokens.add(name)
    for t in list(tokens):
        for d in _DANGEROUS_TOKENS:
            if d in t or t == d:
                return MCPPermissionLevel.DENY

    for t in list(tokens):
        for w in _WRITE_TOKENS:
            if t.startswith(w) or w.rstrip("_") in t:
                return MCPPermissionLevel.ASK

    for t in list(tokens):
        for r in _READ_TOKENS:
            if t.startswith(r) or r in t:
                return MCPPermissionLevel.ALLOW

    # Unknown tools default to ASK (never auto-ALLOW)
    return MCPPermissionLevel.ASK


class MCPToolPolicy:
    """Map classified level to policy action for adapter / service."""

    def decide(
        self,
        tool_name: str,
        *,
        annotations: dict[str, Any] | None = None,
        permission_level: MCPPermissionLevel | None = None,
    ) -> MCPPolicyDecision:
        level = permission_level or classify_mcp_tool(
            tool_name, annotations=annotations
        )
        if level is MCPPermissionLevel.DENY:
            return MCPPolicyDecision(
                MCPPolicyAction.DENY,
                f"MCP tool '{tool_name}' classified as dangerous.",
                level,
            )
        if level is MCPPermissionLevel.ASK:
            return MCPPolicyDecision(
                MCPPolicyAction.ASK,
                f"MCP tool '{tool_name}' may mutate external state; confirmation required.",
                level,
            )
        return MCPPolicyDecision(
            MCPPolicyAction.ALLOW,
            f"MCP tool '{tool_name}' classified as read-only.",
            level,
        )
