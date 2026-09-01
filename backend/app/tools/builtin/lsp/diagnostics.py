"""lsp_diagnostics tool."""

from __future__ import annotations

from typing import Any

from backend.app.lsp.service import LSPService
from backend.app.tools.base import Tool
from backend.app.tools.builtin.lsp._common import lsp_error_result, lsp_tool_result
from backend.app.tools.result import ToolResult
from backend.app.workspace.workspace import Workspace


class LspDiagnosticsTool(Tool):
    def __init__(self, service: LSPService) -> None:
        self._service = service

    @property
    def name(self) -> str:
        return "lsp_diagnostics"

    @property
    def description(self) -> str:
        return (
            "Get language-server diagnostics (errors/warnings) for a file or the workspace. "
            "Use after edits to discover type/syntax issues before running tests. "
            "If LSP is unavailable, continue with read_file/search_code/run_command."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Optional workspace-relative file path",
                },
            },
            "required": [],
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        path = arguments.get("path")
        try:
            diags = self._service.diagnostics(str(path) if path else None)
        except Exception as exc:  # noqa: BLE001
            return lsp_error_result(self.name, exc)

        errors = sum(1 for d in diags if d.severity.value == "error")
        warnings = sum(1 for d in diags if d.severity.value == "warning")
        return lsp_tool_result(
            success=True,
            output={
                "path": path,
                "count": len(diags),
                "errors": errors,
                "warnings": warnings,
                "diagnostics": [d.to_dict() for d in diags],
                "summary": (
                    f"{len(diags)} diagnostics (errors={errors}, warnings={warnings})"
                    if diags
                    else "clean"
                ),
            },
            metadata={
                "tool_name": self.name,
                "path": path,
                "count": len(diags),
                "errors": errors,
                "clean": len(diags) == 0,
            },
        )


def create_lsp_diagnostics_tool(
    workspace: Workspace,
    *,
    service: LSPService | None = None,
) -> LspDiagnosticsTool:
    return LspDiagnosticsTool(service or LSPService(workspace))
