"""search_code：在工作区文本文件中搜索内容。"""

from __future__ import annotations

from typing import Any

from backend.app.tools.base import Tool
from backend.app.tools.builtin.workspace._common import tool_failure
from backend.app.tools.result import ToolResult
from backend.app.workspace.errors import WorkspaceError
from backend.app.workspace.workspace import Workspace


class SearchCodeTool(Tool):
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "search_code"

    @property
    def description(self) -> str:
        return (
            "在工作区文本文件中按子串搜索代码内容，返回 file、line、match。"
            "用于查找函数名、类名、报错字符串等；"
            "按文件名或后缀找文件请用 glob，不要用本工具代替 glob。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "要搜索的文本",
                },
                "path": {
                    "type": "string",
                    "description": "搜索范围目录或文件，默认 '.'",
                },
            },
            "required": ["query"],
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        query = arguments.get("query", "")
        path = arguments.get("path", ".")
        try:
            hits = self._workspace.search(str(query), path=path)
        except WorkspaceError as exc:
            return tool_failure(exc)
        return ToolResult(
            success=True,
            output={"query": query, "hits": hits, "count": len(hits)},
        )
