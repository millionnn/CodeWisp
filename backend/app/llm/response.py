"""LLM 响应领域对象。

将厂商 SDK 的 response.choices[0].message... 关在 LLMClient 内部，
上层（CLI / Agent Loop）只依赖本模块的稳定结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ToolCall:
    """模型请求调用的单个工具（领域侧表示，非 SDK 对象）。"""

    id: str
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    # 原始 JSON 字符串（若有），便于写回 OpenAI 兼容的 assistant.tool_calls
    arguments_raw: str | None = None
    # arguments JSON 解析失败时的错误说明；非空则 Agent 不应调用 Executor
    parse_error: str | None = None


@dataclass(frozen=True)
class LLMResponse:
    """一次 LLM 调用的结构化结果。"""

    content: str | None
    tool_calls: tuple[ToolCall, ...] = ()
    finish_reason: str | None = None
    raw_response: Any | None = None

    @property
    def has_tool_calls(self) -> bool:
        return len(self.tool_calls) > 0

    @property
    def text(self) -> str:
        """便于展示的文本；content 为 None 时返回空串。"""
        return self.content or ""
