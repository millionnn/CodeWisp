"""工具系统相关异常。"""

from backend.app.llm.errors import CodeWispError


class ToolError(CodeWispError):
    """工具系统基础异常。"""


class ToolNotFoundError(ToolError):
    """请求的工具不存在。"""


class ToolRegistrationError(ToolError):
    """工具注册失败（如重复注册、名称为空）。"""


class ToolArgumentError(ToolError):
    """工具参数校验失败。"""
