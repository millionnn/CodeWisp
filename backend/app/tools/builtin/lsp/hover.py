"""lsp_hover tool."""

from __future__ import annotations

from typing import Any

from backend.app.lsp.service import LSPService
from backend.app.tools.base import Tool
from backend.app.tools.builtin.lsp._common import (
    lsp_error_result,
    lsp_tool_result,
    parse_position,
)
from backend.app.tools.result import ToolResult
from backend.app.workspace.workspace import Workspace


class LspHoverTool(Tool):
    def __init__(self, service: LSPService) -> None:
        self._service = service

    @property
    def name(self) -> str:
        return "lsp_hover"

    @property
    def description(self) -> str:
        return (
            "Get hover information (type / docstring summary) at a position "
            "(0-based line/character)."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "line": {"type": "integer"},
                "character": {"type": "integer"},
            },
            "required": ["path", "line", "character"],
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = str(arguments.get("path") or "").strip()
        if not path:
            return lsp_tool_result(success=False, output=None, error="path is required")
        parsed = parse_position(arguments)
        if isinstance(parsed, ToolResult):
            return parsed
        line, character = parsed
        try:
            result = self._service.hover(path, line, character)
        except Exception as exc:  # noqa: BLE001
            return lsp_error_result(self.name, exc)

        return lsp_tool_result(
            success=True,
            output={
                "path": path,
                "line": line,
                "character": character,
                **result.to_dict(),
            },
            metadata={"tool_name": self.name, "path": path},
        )


def create_lsp_hover_tool(
    workspace: Workspace,
    *,
    service: LSPService | None = None,
) -> LspHoverTool:
    return LspHoverTool(service or LSPService(workspace))
