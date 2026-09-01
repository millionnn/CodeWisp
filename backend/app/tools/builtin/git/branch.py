"""git_branch tool."""

from __future__ import annotations

from typing import Any, Callable

from backend.app.git.service import GitService
from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.handler import PermissionHandler
from backend.app.permissions.request import PermissionRequest
from backend.app.tools.base import Tool
from backend.app.tools.builtin.git._common import (
    git_tool_result,
    handle_git_policy,
    permission_required_result,
    policy_denied_result,
    user_denied_result,
)
from backend.app.tools.result import ToolResult
from backend.app.workspace.workspace import Workspace


class GitBranchTool(Tool):
    def __init__(
        self,
        service: GitService,
        *,
        permission_handler: PermissionHandler | None = None,
        session_id: str | None = None,
        agent_run_id: str | None = None,
        on_permission_wait: Callable[[PermissionRequest], None] | None = None,
        on_permission_resolved: Callable[
            [PermissionRequest, PermissionDecision | None], None
        ] | None = None,
    ) -> None:
        self._service = service
        self._permission_handler = permission_handler
        self._session_id = session_id
        self._agent_run_id = agent_run_id
        self._on_permission_wait = on_permission_wait
        self._on_permission_resolved = on_permission_resolved

    @property
    def name(self) -> str:
        return "git_branch"

    @property
    def description(self) -> str:
        return (
            "List, create, or switch Git branches. "
            "action=list (default) shows local branches; "
            "create/switch require user permission."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["list", "create", "switch"],
                    "description": "Branch action (default list)",
                },
                "name": {
                    "type": "string",
                    "description": "Branch name (required for create/switch)",
                },
            },
            "required": [],
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        action = str(arguments.get("action") or "list").strip().lower()
        name = arguments.get("name")

        if action == "list":
            try:
                branches = self._service.list_branches()
                current = self._service.current_branch()
            except Exception as exc:  # noqa: BLE001
                return git_tool_result(
                    success=False,
                    output=None,
                    error=str(exc),
                    metadata={"tool_name": self.name},
                )
            return git_tool_result(
                success=True,
                output={
                    "current": current,
                    "branches": [b.to_dict() for b in branches],
                },
                metadata={"tool_name": self.name, "action": "list"},
            )

        if not name or not str(name).strip():
            return git_tool_result(
                success=False,
                output=None,
                error=f"git_branch action={action} 需要 name 参数。",
                metadata={"tool_name": self.name},
            )

        subcommand = "branch" if action == "create" else "switch"
        allowed, decision, perm_req = handle_git_policy(
            tool_name=self.name,
            subcommand=subcommand,
            args=(str(name).strip(),),
            service=self._service,
            permission_handler=self._permission_handler,
            session_id=self._session_id,
            agent_run_id=self._agent_run_id,
            on_permission_wait=self._on_permission_wait,
            on_permission_resolved=self._on_permission_resolved,
        )
        assert decision is not None

        if decision.action.value == "deny":
            return policy_denied_result(self.name, decision)

        if not allowed:
            if perm_req is None:
                return permission_required_result(self.name, decision)
            return user_denied_result(self.name, perm_req, decision)

        try:
            if action == "create":
                branch = self._service.create_branch(str(name).strip())
                output = {"created": branch.to_dict()}
            else:
                switched = self._service.switch_branch(str(name).strip())
                output = {"switched_to": switched}
        except Exception as exc:  # noqa: BLE001
            return git_tool_result(
                success=False,
                output=None,
                error=str(exc),
                metadata={"tool_name": self.name, "action": action},
            )

        meta: dict[str, Any] = {"tool_name": self.name, "action": action}
        if perm_req:
            meta["permission_decision"] = PermissionDecision.ALLOW.value
            meta["permission_request_id"] = perm_req.request_id
        return git_tool_result(success=True, output=output, metadata=meta)


def create_git_branch_tool(
    workspace: Workspace,
    *,
    permission_handler: PermissionHandler | None = None,
    session_id: str | None = None,
    agent_run_id: str | None = None,
    on_permission_wait: Callable[[PermissionRequest], None] | None = None,
    on_permission_resolved: Callable[
        [PermissionRequest, PermissionDecision | None], None
    ] | None = None,
) -> GitBranchTool:
    return GitBranchTool(
        GitService(workspace),
        permission_handler=permission_handler,
        session_id=session_id,
        agent_run_id=agent_run_id,
        on_permission_wait=on_permission_wait,
        on_permission_resolved=on_permission_resolved,
    )
