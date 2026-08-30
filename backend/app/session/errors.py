"""Session / AgentService 领域错误。"""

from __future__ import annotations

from backend.app.llm.errors import CodeWispError


class SessionError(CodeWispError):
    """Session 相关错误基类。"""


class SessionNotFoundError(SessionError):
    """Session 不存在。"""


class SessionBusyError(SessionError):
    """同一 Session 上已有 Agent 在运行。"""


class InvalidSessionError(SessionError):
    """Session 参数或状态非法。"""


class InvalidMessageError(SessionError):
    """用户消息非法。"""


class InvalidWorkspaceError(SessionError):
    """Session 绑定的 workspace 无效。"""
