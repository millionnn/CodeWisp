"""write_file：在工作区内创建或覆盖文本文件。"""

from __future__ import annotations

from typing import Any

from backend.app.tools.base import Tool
from backend.app.tools.builtin.workspace._common import tool_failure
from backend.app.tools.result import ToolResult
from backend.app.workspace.errors import WorkspaceError
from backend.app.workspace.workspace import Workspace


class WriteFileTool(Tool):
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "write_file"

    @property
    def description(self) -> str:
        return (
            "在工作区内创建新的 UTF-8 文本文件。"
            "默认 overwrite=false：若目标文件已存在则拒绝写入，避免无意覆盖；"
            "需要覆盖已有文件时须显式传入 overwrite=true。"
            "若父目录不存在，将在 workspace 路径边界内自动创建。"
            "写入完成后可通过 read_file 核对文件内容。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "相对 workspace 的目标文件路径",
                },
                "content": {
                    "type": "string",
                    "description": "要写入的完整文件内容（UTF-8 文本）",
                },
                "overwrite": {
                    "type": "boolean",
                    "description": "若文件已存在是否允许覆盖，默认 false",
                    "default": False,
                },
            },
            "required": ["path", "content"],
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = arguments.get("path", "")
        content = arguments.get("content")
        overwrite = arguments.get("overwrite", False)
        if content is None:
            return ToolResult(success=False, output=None, error="缺少 content 参数。")
        if not isinstance(content, str):
            return ToolResult(success=False, output=None, error="content 必须为字符串。")
        try:
            data = self._workspace.write_text(
                str(path),
                content,
                overwrite=bool(overwrite),
            )
        except (WorkspaceError, TypeError, ValueError) as exc:
            return tool_failure(exc)
        return ToolResult(
            success=True,
            output=data,
            metadata={
                "tool_name": self.name,
                "path": data["path"],
                "created": data["created"],
                "overwritten": data["overwritten"],
            },
        )
