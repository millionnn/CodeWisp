"""Permission 领域错误。"""

from __future__ import annotations

from backend.app.llm.errors import CodeWispError


class PermissionError(CodeWispError):
    """Permission 领域基础错误。"""


class InvalidPermissionDecisionError(PermissionError):
    """非法的授权决定。"""


class PermissionInterruptedError(PermissionError):
    """等待用户授权时被中断（EOF / Ctrl+C）。"""
