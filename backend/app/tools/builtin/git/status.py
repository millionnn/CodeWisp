"""git_status tool."""

from __future__ import annotations

from typing import Any

from backend.app.git.errors import GitNotRepositoryError
from backend.app.git.service import GitService
from backend.app.tools.base import Tool
from backend.app.tools.builtin.git._common import git_tool_result
from backend.app.tools.result import ToolResult
from backend.app.workspace.workspace import Workspace


class GitStatusTool(Tool):
    def __init__(self, service: GitService) -> None:
        self._service = service

    @property
    def name(self) -> str:
        return "git_status"

    @property
    def description(self) -> str:
        return (
            "Inspect the current Git repository status. "
            "Use this when you need to understand the current repository state "
            "before making changes or when summarizing work."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        try:
            result = self._service.status()
        except Exception as exc:  # noqa: BLE001
            return git_tool_result(
                success=False,
                output=None,
                error=str(exc),
                metadata={"tool_name": self.name},
            )

        if hasattr(result, "is_git_repository"):
            return git_tool_result(
                success=True,
                output=result.to_dict(),
                metadata={"tool_name": self.name, "is_git_repository": False},
            )

        return git_tool_result(
            success=True,
            output={
                **result.to_dict(),
                "summary": result.render_summary(),
            },
            metadata={
                "tool_name": self.name,
                "branch": result.branch,
                "clean": result.clean,
            },
        )


def create_git_status_tool(workspace: Workspace) -> GitStatusTool:
    return GitStatusTool(GitService(workspace))
