"""LLM 响应领域对象。

将厂商 SDK 的 response.choices[0].message... 关在 LLMClient 内部，
上层（CLI / Agent Loop）只依赖本模块的稳定结构。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from backend.app.session.ids import new_tool_call_id


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

    def with_stable_id(self) -> ToolCall:
        """若 id 为空则分配 ``tc_<uuid>``；已有非空 id 则原样返回。"""
        if (self.id or "").strip():
            return self
        return ToolCall(
            id=new_tool_call_id(),
            name=self.name,
            arguments=dict(self.arguments),
            arguments_raw=self.arguments_raw,
            parse_error=self.parse_error,
        )

    def to_persistence_dict(self) -> dict[str, Any]:
        """完整领域序列化（含 arguments_raw / parse_error），供持久化 round-trip。"""
        return {
            "id": self.id,
            "name": self.name,
            "arguments": dict(self.arguments),
            "arguments_raw": self.arguments_raw,
            "parse_error": self.parse_error,
        }

    @classmethod
    def from_persistence_dict(cls, data: dict[str, Any]) -> ToolCall:
        if not isinstance(data, dict):
            raise TypeError("ToolCall.from_persistence_dict 需要 dict")
        name = data.get("name")
        if not isinstance(name, str):
            raise ValueError("ToolCall.name 必须是字符串")
        raw_id = data.get("id", "")
        if raw_id is None:
            raw_id = ""
        if not isinstance(raw_id, str):
            raise ValueError("ToolCall.id 必须是字符串")
        arguments = data.get("arguments") or {}
        if not isinstance(arguments, dict):
            raise ValueError("ToolCall.arguments 必须是 dict")
        arguments_raw = data.get("arguments_raw")
        if arguments_raw is not None and not isinstance(arguments_raw, str):
            raise ValueError("ToolCall.arguments_raw 必须是字符串或 None")
        parse_error = data.get("parse_error")
        if parse_error is not None and not isinstance(parse_error, str):
            raise ValueError("ToolCall.parse_error 必须是字符串或 None")
        return cls(
            id=raw_id,
            name=name,
            arguments=dict(arguments),
            arguments_raw=arguments_raw,
            parse_error=parse_error,
        ).with_stable_id()


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
