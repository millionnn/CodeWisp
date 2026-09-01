"""lsp_symbols tool."""

from __future__ import annotations

from typing import Any

from backend.app.lsp.service import LSPService
from backend.app.tools.base import Tool
from backend.app.tools.builtin.lsp._common import lsp_error_result, lsp_tool_result
from backend.app.tools.result import ToolResult
from backend.app.workspace.workspace import Workspace


class LspSymbolsTool(Tool):
    def __init__(self, service: LSPService) -> None:
        self._service = service

    @property
    def name(self) -> str:
        return "lsp_symbols"

    @property
    def description(self) -> str:
        return (
            "List document symbols (classes, functions, methods) for a file. "
            "Use to understand file structure before editing."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Workspace-relative file path",
                },
            },
            "required": ["path"],
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = str(arguments.get("path") or "").strip()
        if not path:
            return lsp_tool_result(success=False, output=None, error="path is required")
        try:
            symbols = self._service.symbols(path)
        except Exception as exc:  # noqa: BLE001
            return lsp_error_result(self.name, exc)

        tree_lines: list[str] = []
        for sym in symbols:
            tree_lines.extend(sym.render_tree())

        return lsp_tool_result(
            success=True,
            output={
                "path": path,
                "count": len(symbols),
                "symbols": [s.to_dict() for s in symbols],
                "tree": "\n".join(tree_lines),
            },
            metadata={
                "tool_name": self.name,
                "path": path,
                "count": len(symbols),
            },
        )


def create_lsp_symbols_tool(
    workspace: Workspace,
    *,
    service: LSPService | None = None,
) -> LspSymbolsTool:
    return LspSymbolsTool(service or LSPService(workspace))
