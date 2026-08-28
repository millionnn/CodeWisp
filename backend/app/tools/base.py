"""Tool 抽象基类。

Tool 不依赖 CLI，也不依赖具体 LLM Provider。
未来 Agent Runtime / Web API 可直接复用同一套工具定义。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from backend.app.tools.result import ToolResult


class Tool(ABC):
    """可注册、可执行的本地工具。"""

    @property
    @abstractmethod
    def name(self) -> str:
        """全局唯一工具名。"""

    @property
    @abstractmethod
    def description(self) -> str:
        """给人或未来 LLM 阅读的功能说明。"""

    @property
    @abstractmethod
    def parameters(self) -> dict[str, Any]:
        """JSON Schema 风格的参数描述（object）。"""

    @abstractmethod
    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        """执行工具。参数已由 Executor 做基础校验时可直接使用。"""

    def to_schema(self) -> dict[str, Any]:
        """导出供未来 LLM tool calling 使用的工具描述。"""
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": self.parameters,
            },
        }
