"""git_log tool."""

from __future__ import annotations

from typing import Any

from backend.app.git.service import GitService
from backend.app.tools.base import Tool
from backend.app.tools.builtin.git._common import git_tool_result
from backend.app.tools.result import ToolResult
from backend.app.workspace.workspace import Workspace


class GitLogTool(Tool):
    def __init__(self, service: GitService) -> None:
        self._service = service

    @property
    def name(self) -> str:
        return "git_log"

    @property
    def description(self) -> str:
        return (
            "Show recent Git commit history. "
            "Use this when repository history may provide useful context. "
            "Does not load entire history — limit defaults to 20."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "limit": {
                    "type": "integer",
                    "description": "Number of commits to show (default 20, max 100)",
                },
            },
            "required": [],
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        limit = arguments.get("limit", 20)
        try:
            limit = int(limit)
        except (TypeError, ValueError):
            limit = 20
        try:
            commits = self._service.log(limit=limit)
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
                "commits": [c.to_dict() for c in commits],
                "count": len(commits),
            },
            metadata={"tool_name": self.name, "count": len(commits)},
        )


def create_git_log_tool(workspace: Workspace) -> GitLogTool:
    return GitLogTool(GitService(workspace))
