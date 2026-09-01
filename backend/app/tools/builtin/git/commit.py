"""git_commit tool — preview + permission + commit."""

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


class GitCommitTool(Tool):
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
        return "git_commit"

    @property
    def description(self) -> str:
        return (
            "Create a Git commit with the given message. "
            "Use this ONLY when the user explicitly asks you to commit changes. "
            "This is not a regular write tool — it requires user approval. "
            "Always inspect git_status and git_diff before committing."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "message": {
                    "type": "string",
                    "description": "Commit message",
                },
                "paths": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Optional paths to stage (default: all changes)",
                },
            },
            "required": ["message"],
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        message = str(arguments.get("message") or "").strip()
        if not message:
            return git_tool_result(
                success=False,
                output=None,
                error="commit message 不能为空。",
                metadata={"tool_name": self.name},
            )

        raw_paths = arguments.get("paths")
        paths: list[str] | None = None
        if raw_paths is not None:
            if not isinstance(raw_paths, list):
                return git_tool_result(
                    success=False,
                    output=None,
                    error="paths 必须是字符串数组。",
                    metadata={"tool_name": self.name},
                )
            paths = [str(p) for p in raw_paths]

        # Build commit preview first
        try:
            preview = self._service.build_commit_preview(message, paths)
        except Exception as exc:  # noqa: BLE001
            return git_tool_result(
                success=False,
                output=None,
                error=str(exc),
                metadata={"tool_name": self.name},
            )

        preview_dict = preview.to_dict()
        preview_dict["rendered"] = preview.render()

        # Policy check for commit (ASK)
        commit_args: tuple[str, ...] = ("-m", message)
        allowed, decision, perm_req = handle_git_policy(
            tool_name=self.name,
            subcommand="commit",
            args=commit_args,
            service=self._service,
            permission_handler=self._permission_handler,
            session_id=self._session_id,
            agent_run_id=self._agent_run_id,
            on_permission_wait=self._on_permission_wait,
            on_permission_resolved=self._on_permission_resolved,
            reason_override=(
                f"即将提交 Git commit:\n{preview.render()}\n\n需要用户授权。"
            ),
        )
        assert decision is not None

        if decision.action.value == "deny":
            return policy_denied_result(self.name, decision)

        if not allowed:
            if perm_req is None:
                return permission_required_result(
                    self.name,
                    decision,
                    preview=preview_dict,
                )
            return user_denied_result(self.name, perm_req, decision)

        try:
            result = self._service.commit(message, paths)
        except Exception as exc:  # noqa: BLE001
            return git_tool_result(
                success=False,
                output={"commit_preview": preview_dict},
                error=str(exc),
                metadata={"tool_name": self.name},
            )

        meta: dict[str, Any] = {
            "tool_name": self.name,
            "commit_id": result.get("commit_id"),
            "branch": result.get("branch"),
        }
        if perm_req:
            meta["permission_decision"] = PermissionDecision.ALLOW.value
            meta["permission_request_id"] = perm_req.request_id

        return git_tool_result(
            success=True,
            output={
                **result,
                "commit_preview": preview_dict,
            },
            metadata=meta,
        )


def create_git_commit_tool(
    workspace: Workspace,
    *,
    permission_handler: PermissionHandler | None = None,
    session_id: str | None = None,
    agent_run_id: str | None = None,
    on_permission_wait: Callable[[PermissionRequest], None] | None = None,
    on_permission_resolved: Callable[
        [PermissionRequest, PermissionDecision | None], None
    ] | None = None,
) -> GitCommitTool:
    return GitCommitTool(
        GitService(workspace),
        permission_handler=permission_handler,
        session_id=session_id,
        agent_run_id=agent_run_id,
        on_permission_wait=on_permission_wait,
        on_permission_resolved=on_permission_resolved,
    )
