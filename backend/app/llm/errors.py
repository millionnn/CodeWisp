"""CodeWisp 领域异常。

这些异常应在 UI 边界（CLI / 未来 API）捕获，并转成用户可读提示，
避免把原始 Python traceback 直接展示给普通用户。
"""


class CodeWispError(Exception):
    """CodeWisp 基础异常。"""


class ConfigError(CodeWispError):
    """配置无效或缺失（如 API Key、模型名）。"""


class LLMRequestError(CodeWispError):
    """LLM API 请求失败（HTTP 错误、鉴权失败、限流等）。"""


class LLMNetworkError(CodeWispError):
    """访问 LLM API 时发生网络错误。"""
