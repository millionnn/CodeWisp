"""Execution Layer：语言无关的受控命令执行（V0.4-C）。

本包不依赖 AgentLoop；由 run_command Tool 接入。
"""

from backend.app.execution.errors import (
    ExecutionError,
    InvalidExecutionRequestError,
)
from backend.app.execution.policy import (
    CommandPolicy,
    ExecutionDecision,
    PolicyAction,
)
from backend.app.execution.request import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    ExecutionRequest,
)
from backend.app.execution.result import ExecutionResult, PermissionRequired
from backend.app.execution.service import DEFAULT_MAX_OUTPUT_CHARS, ExecutionService

__all__ = [
    "DEFAULT_MAX_OUTPUT_CHARS",
    "DEFAULT_TIMEOUT_SECONDS",
    "MAX_TIMEOUT_SECONDS",
    "CommandPolicy",
    "ExecutionDecision",
    "ExecutionError",
    "ExecutionRequest",
    "ExecutionResult",
    "ExecutionService",
    "InvalidExecutionRequestError",
    "PermissionRequired",
    "PolicyAction",
]
