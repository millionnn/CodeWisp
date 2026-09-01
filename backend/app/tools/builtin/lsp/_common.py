"""Shared helpers for LSP tools."""

from __future__ import annotations

from typing import Any

from backend.app.lsp.errors import LspError
from backend.app.tools.result import ToolResult


def lsp_tool_result(
    *,
    success: bool,
    output: Any,
    error: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> ToolResult:
    meta = metadata or {}
    meta.setdefault("tool_category", "lsp")
    return ToolResult(success=success, output=output, error=error, metadata=meta)


def lsp_error_result(tool_name: str, exc: Exception) -> ToolResult:
    """Structured failure — never crash AgentLoop."""
    unavailable = isinstance(exc, LspError)
    return lsp_tool_result(
        success=False,
        output={
            "unavailable": unavailable,
            "error_type": type(exc).__name__,
        },
        error=str(exc),
        metadata={
            "tool_name": tool_name,
            "lsp_unavailable": unavailable,
        },
    )


def parse_position(arguments: dict[str, Any]) -> tuple[int, int] | ToolResult:
    """Accept 0-based line/character; also accept 1-based line via line_1based."""
    if "line_1based" in arguments and arguments.get("line") is None:
        try:
            line = int(arguments["line_1based"]) - 1
        except (TypeError, ValueError):
            return lsp_tool_result(
                success=False,
                output=None,
                error="line_1based must be an integer",
            )
    else:
        try:
            line = int(arguments.get("line", 0))
        except (TypeError, ValueError):
            return lsp_tool_result(
                success=False,
                output=None,
                error="line must be an integer (0-based)",
            )
    try:
        character = int(arguments.get("character", 0))
    except (TypeError, ValueError):
        return lsp_tool_result(
            success=False,
            output=None,
            error="character must be an integer (0-based)",
        )
    if line < 0 or character < 0:
        return lsp_tool_result(
            success=False,
            output=None,
            error="line and character must be >= 0 (0-based LSP positions)",
        )
    return line, character
