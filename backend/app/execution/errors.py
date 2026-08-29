"""Execution Layer 异常。"""


class ExecutionError(Exception):
    """命令执行层失败。"""


class InvalidExecutionRequestError(ExecutionError):
    """ExecutionRequest 非法（空命令、超时越界等）。"""
