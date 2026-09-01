"""Shared helpers for Git tools."""

from __future__ import annotations

from typing import Any, Callable

from backend.app.git.policy import GitPolicyAction, GitPolicyDecision
from backend.app.git.service import GitService
from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.errors import PermissionInterruptedError
from backend.app.permissions.handler import PermissionHandler
from backend.app.permissions.request import PermissionRequest
from backend.app.tools.result import ToolResult


def git_tool_result(
    *,
    success: bool,
    output: Any,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ToolResult:
    base = metadata or {}
    base.setdefault("tool_category", "git")
    return ToolResult(success=success, output=output, error=error, metadata=base)


def handle_git_policy(
    *,
    tool_name: str,
    subcommand: str,
    args: tuple[str, ...],
    service: GitService,
    permission_handler: PermissionHandler | None,
    session_id: str | None,
    agent_run_id: str | None,
    on_permission_wait: Callable[[PermissionRequest], None] | None,
    on_permission_resolved: Callable[[PermissionRequest, PermissionDecision | None], None] | None,
    reason_override: str | None = None,
) -> tuple[bool, GitPolicyDecision | None, PermissionRequest | None]:
    """Returns (allowed, decision, permission_request).

    allowed=True means proceed; False means stop (DENY or no handler on ASK).
    """
    decision = service.policy_decide(subcommand, args)

    if decision.action is GitPolicyAction.ALLOW:
        return True, decision, None

    if decision.action is GitPolicyAction.DENY:
        return False, decision, None

    # ASK
    reason = reason_override or decision.reason
    if permission_handler is None:
        return False, decision, None

    perm_req = PermissionRequest(
        command="git",
        args=(subcommand, *args),
        cwd=".",
        reason=reason,
        tool_name=tool_name,
        session_id=session_id,
        agent_run_id=agent_run_id,
    )
    if on_permission_wait is not None:
        on_permission_wait(perm_req)

    try:
        user_decision = permission_handler.request(perm_req)
    except PermissionInterruptedError:
        if on_permission_resolved is not None:
            on_permission_resolved(perm_req, None)
        return False, decision, perm_req

    if on_permission_resolved is not None:
        on_permission_resolved(perm_req, user_decision)

    if user_decision is PermissionDecision.ALLOW:
        return True, decision, perm_req

    return False, decision, perm_req


def policy_denied_result(
    tool_name: str,
    decision: GitPolicyDecision,
) -> ToolResult:
    return git_tool_result(
        success=False,
        output={"denied": True, "decision": decision.to_dict()},
        error=decision.reason,
        metadata={"tool_name": tool_name, "policy_action": decision.action.value},
    )


def permission_required_result(
    tool_name: str,
    decision: GitPolicyDecision,
    *,
    preview: dict[str, Any] | None = None,
) -> ToolResult:
    output: dict[str, Any] = {
        "permission_required": True,
        "decision": decision.to_dict(),
    }
    if preview:
        output["commit_preview"] = preview
    return git_tool_result(
        success=False,
        output=output,
        error=decision.reason,
        metadata={
            "tool_name": tool_name,
            "policy_action": decision.action.value,
            "permission_required": True,
        },
    )


def user_denied_result(
    tool_name: str,
    perm_req: PermissionRequest,
    decision: GitPolicyDecision,
) -> ToolResult:
    return git_tool_result(
        success=False,
        output={
            "denied": True,
            "user_denied": True,
            "permission_request_id": perm_req.request_id,
            "decision": decision.to_dict(),
        },
        error="用户拒绝执行该 Git 操作（DENY）。",
        metadata={
            "tool_name": tool_name,
            "policy_action": decision.action.value,
            "permission_decision": PermissionDecision.DENY.value,
        },
    )
