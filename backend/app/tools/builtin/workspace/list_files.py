"""list_files：列出工作区目录条目。"""

from __future__ import annotations

from typing import Any

from backend.app.tools.base import Tool
from backend.app.tools.builtin.workspace._common import tool_failure
from backend.app.tools.result import ToolResult
from backend.app.workspace.errors import WorkspaceError
from backend.app.workspace.workspace import Workspace


class ListFilesTool(Tool):
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "list_files"

    @property
    def description(self) -> str:
        return (
            "列出工作区内某目录下的文件与子目录。"
            "默认只列出一层（max_depth=1），不会递归整个仓库；需要更深时增大 max_depth。"
            "了解仓库结构或进入某个目录前优先使用本工具。"
            "返回每项的相对路径与类型（file/directory）。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "相对 workspace 的目录路径，默认 '.'",
                },
                "max_depth": {
                    "type": "integer",
                    "description": "递归深度，默认 1（仅当前目录）",
                },
            },
            "required": [],
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = arguments.get("path", ".")
        max_depth = arguments.get("max_depth", 1)
        try:
            entries = self._workspace.list(path, max_depth=int(max_depth))
        except (WorkspaceError, TypeError, ValueError) as exc:
            return tool_failure(exc)
        return ToolResult(
            success=True,
            output={"path": path or ".", "entries": entries, "count": len(entries)},
        )
