"""git_diff tool."""

from __future__ import annotations

from typing import Any

from backend.app.git.service import GitService
from backend.app.tools.base import Tool
from backend.app.tools.builtin.git._common import git_tool_result
from backend.app.tools.result import ToolResult
from backend.app.workspace.workspace import Workspace


class GitDiffTool(Tool):
    def __init__(self, service: GitService) -> None:
        self._service = service

    @property
    def name(self) -> str:
        return "git_diff"

    @property
    def description(self) -> str:
        return (
            "Show Git diff for working tree or staged changes. "
            "Use this when you need to inspect code changes before verification or commit. "
            "Set staged=true for staged diff; optional path for a specific file."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Optional file path (relative to workspace)",
                },
                "staged": {
                    "type": "boolean",
                    "description": "If true, show staged diff (default false)",
                },
            },
            "required": [],
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = arguments.get("path")
        staged = bool(arguments.get("staged", False))
        try:
            diff = self._service.diff(
                path=str(path) if path else None,
                staged=staged,
            )
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
                **diff.to_dict(),
                "summary": diff.render_summary(),
            },
            metadata={
                "tool_name": self.name,
                "staged": staged,
                "file_count": len(diff.files),
                "additions": diff.total_additions,
                "deletions": diff.total_deletions,
            },
        )


def create_git_diff_tool(workspace: Workspace) -> GitDiffTool:
    return GitDiffTool(GitService(workspace))
