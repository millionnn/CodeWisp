"""Agent 运行时相关异常。"""

from backend.app.llm.errors import CodeWispError


class AgentError(CodeWispError):
    """Agent 运行时基础异常。"""
