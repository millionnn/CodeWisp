"""LLM 响应领域对象。

将厂商 SDK 的 response.choices[0].message... 关在 LLMClient 内部，
上层（CLI / 未来 Agent Loop）只依赖本模块的稳定结构。

当前版本以文本对话为主；tool_calls 已预留，供 V0.3 Agent Loop 使用，
本阶段不会自动执行工具。
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
