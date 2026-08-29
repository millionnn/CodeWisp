"""Workspace 类工具的共享辅助。"""

from __future__ import annotations

from backend.app.tools.result import ToolResult


def tool_failure(exc: Exception) -> ToolResult:
    """将 Workspace / 参数异常转为统一失败结果。"""
    return ToolResult(success=False, output=None, error=str(exc))
