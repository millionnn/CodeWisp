"""edit_file：对已有文件做确定性局部替换。"""

from __future__ import annotations

from typing import Any

from backend.app.tools.base import Tool
from backend.app.tools.builtin.workspace._common import tool_failure
from backend.app.tools.result import ToolResult
from backend.app.workspace.errors import WorkspaceError
from backend.app.workspace.workspace import Workspace


class EditFileTool(Tool):
    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    @property
    def name(self) -> str:
        return "edit_file"

    @property
    def description(self) -> str:
        return (
            "对工作区内已有文本文件执行精确、确定性的局部修改。"
            "使用 old_text 精确匹配目标文本，并将其替换为 new_text。"
            "仅当实际匹配次数恰好等于 expected_replacements（默认 1）时才执行写入；"
            "匹配次数与预期不一致时一律失败，不进行模糊匹配或猜测性修改。"
            "修改前应确保已获得足够的文件上下文（通常可通过 read_file 获取）；"
            "修改后可通过 read_file 检查修改结果。"
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
                "old_text": {
                    "type": "string",
                    "description": "需要被精确匹配并替换的原始文本（不可为空）",
                },
                "new_text": {
                    "type": "string",
                    "description": "替换后的文本",
                },
                "expected_replacements": {
                    "type": "integer",
                    "description": "预期匹配/替换次数，默认 1；必须与实际匹配次数完全一致",
                    "default": 1,
                },
            },
            "required": ["path", "old_text", "new_text"],
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = arguments.get("path", "")
        old_text = arguments.get("old_text")
        new_text = arguments.get("new_text")
        expected = arguments.get("expected_replacements", 1)
        try:
            data = self._workspace.replace_text(
                str(path),
                str(old_text) if old_text is not None else "",
                str(new_text) if new_text is not None else "",
                expected_replacements=int(expected) if expected is not None else 1,
            )
        except (WorkspaceError, TypeError, ValueError) as exc:
            return tool_failure(exc)
        return ToolResult(
            success=True,
            output=data,
            metadata={
                "tool_name": self.name,
                "path": data["path"],
                "replacements": data["replacements"],
            },
        )
