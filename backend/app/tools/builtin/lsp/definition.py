"""lsp_definition tool."""

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


class LspDefinitionTool(Tool):
    def __init__(self, service: LSPService) -> None:
        self._service = service

    @property
    def name(self) -> str:
        return "lsp_definition"

    @property
    def description(self) -> str:
        return (
            "Go to definition of the symbol at a position (0-based line/character). "
            "Use when you need to locate where a name is defined."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Workspace-relative file path"},
                "line": {"type": "integer", "description": "0-based line number"},
                "character": {"type": "integer", "description": "0-based character offset"},
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
            result = self._service.definition(path, line, character)
        except Exception as exc:  # noqa: BLE001
            return lsp_error_result(self.name, exc)

        return lsp_tool_result(
            success=True,
            output={
                "path": path,
                "line": line,
                "character": character,
                **result.to_dict(),
                "count": len(result.locations),
            },
            metadata={
                "tool_name": self.name,
                "path": path,
                "count": len(result.locations),
            },
        )


def create_lsp_definition_tool(
    workspace: Workspace,
    *,
    service: LSPService | None = None,
) -> LspDefinitionTool:
    return LspDefinitionTool(service or LSPService(workspace))
