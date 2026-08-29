"""glob：按文件名模式查找文件。"""

from __future__ import annotations

from typing import Any

from backend.app.tools.base import Tool
from backend.app.tools.builtin.workspace._common import tool_failure
from backend.app.tools.result import ToolResult
from backend.app.workspace.errors import WorkspaceError
from backend.app.workspace.workspace import Workspace


class GlobTool(Tool):
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "glob"

    @property
    def description(self) -> str:
        return (
            "按文件名模式查找文件（如 **/*.py、tests/**/*.py、**/loop.py）。"
            "已知或可猜测文件名/后缀时用本工具定位路径；"
            "若要按代码内容（符号、字符串）查找，请改用 search_code。"
        )

# 定义工具参数，pattern 为 glob 模式，path 为搜索起始目录，默认 '.'
    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "pattern": {
                    "type": "string",
                    "description": "glob 模式，例如 '**/*.py'",
                },
                "path": {
                    "type": "string",
                    "description": "搜索起始目录，相对 workspace，默认 '.'",
                },
            },
            "required": ["pattern"],
        }


    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        pattern = arguments.get("pattern", "")
        path = arguments.get("path", ".")
        try:
            matches = self._workspace.glob(str(pattern), path=path)
        except WorkspaceError as exc:
            return tool_failure(exc)
        return ToolResult(
            success=True,
            output={"pattern": pattern, "matches": matches, "count": len(matches)},
        )
