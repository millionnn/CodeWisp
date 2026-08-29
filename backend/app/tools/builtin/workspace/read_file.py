"""read_file：读取工作区内文本文件。"""

from __future__ import annotations

from typing import Any

from backend.app.tools.base import Tool
from backend.app.tools.builtin.workspace._common import tool_failure
from backend.app.tools.result import ToolResult
from backend.app.workspace.errors import WorkspaceError
from backend.app.workspace.workspace import Workspace


class ReadFileTool(Tool):
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "read_file"

    @property
    def description(self) -> str:
        return (
            "读取工作区内的文本文件内容（UTF-8）。"
            "在已通过 list_files / glob / search_code 得到路径后，用本工具查看具体代码。"
            "可选用 start_line/end_line 分段读取；二进制或超大文件会返回错误。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "相对 workspace 的文件路径",
                },
                "start_line": {
                    "type": "integer",
                    "description": "起始行号（从 1 开始，可选）",
                },
                "end_line": {
                    "type": "integer",
                    "description": "结束行号（含，可选）",
                },
                "max_bytes": {
                    "type": "integer",
                    "description": "最大读取字节数，默认 100000",
                },
            },
            "required": ["path"],
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = arguments.get("path", "")
        start_line = arguments.get("start_line")
        end_line = arguments.get("end_line")
        max_bytes = arguments.get("max_bytes")
        kwargs: dict[str, Any] = {}
        if start_line is not None:
            kwargs["start_line"] = int(start_line)
        if end_line is not None:
            kwargs["end_line"] = int(end_line)
        if max_bytes is not None:
            kwargs["max_bytes"] = int(max_bytes)
        try:
            data = self._workspace.read(str(path), **kwargs)
        except (WorkspaceError, TypeError, ValueError) as exc:
            return tool_failure(exc)
        return ToolResult(success=True, output=data)
