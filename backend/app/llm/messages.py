"""对话消息与会话历史。

支持 system / user / assistant / tool，以及 assistant 的 tool_calls。
不做上下文压缩或 memory（留给后续版本）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from backend.app.llm.response import ToolCall

Role = Literal["system", "user", "assistant", "tool"]

ALLOWED_ROLES: frozenset[str] = frozenset({"system", "user", "assistant", "tool"})


@dataclass(frozen=True)
class Message:
    """单条聊天消息（可含 tool_calls 或 tool_call_id）。"""

    role: Role
    content: str | None = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None

    def __post_init__(self) -> None:
        if self.role not in ALLOWED_ROLES:
            raise ValueError(f"不支持的角色: {self.role!r}")
        if self.content is not None and not isinstance(self.content, str):
            raise TypeError("content 必须是字符串或 None")
        if self.role == "tool" and not self.tool_call_id:
            raise ValueError("tool 消息必须包含 tool_call_id")

    def to_dict(self) -> dict[str, Any]:
        """序列化为 OpenAI 兼容的 chat message 结构。"""
        if self.role == "tool":
            return {
                "role": "tool",
                "tool_call_id": self.tool_call_id,
                "content": self.content or "",
            }

        payload: dict[str, Any] = {
            "role": self.role,
            "content": self.content,
        }
        if self.role == "assistant" and self.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": tc.id,
                    "type": "function",
                    "function": {
                        "name": tc.name,
                        "arguments": _tool_arguments_for_api(tc),
                    },
                }
                for tc in self.tool_calls
            ]
        return payload


def _tool_arguments_for_api(tc: ToolCall) -> str:
    if tc.arguments_raw is not None:
        return tc.arguments_raw
    return json.dumps(tc.arguments, ensure_ascii=False)


@dataclass
class Conversation:
    """内存中的多轮对话历史（追加式，无压缩）。"""

    messages: list[Message] = field(default_factory=list)

    def add(self, role: Role, content: str | None) -> Message:
        """追加一条简单文本消息。"""
        message = Message(role=role, content=content)
        self.messages.append(message)
        return message

    def add_user(self, content: str) -> Message:
        return self.add("user", content)

    def add_assistant(self, content: str | None) -> Message:
        return self.add("assistant", content)

    def add_system(self, content: str) -> Message:
        return self.add("system", content)

    def add_assistant_tool_calls(
        self,
        content: str | None,
        tool_calls: tuple[ToolCall, ...] | list[ToolCall],
    ) -> Message:
        """追加带 tool_calls 的 assistant 消息。"""
        calls = tuple(tool_calls)
        message = Message(role="assistant", content=content, tool_calls=calls)
        self.messages.append(message)
        return message

    def add_tool_result(self, tool_call_id: str, content: str) -> Message:
        """追加 tool observation（工具执行结果）。"""
        message = Message(role="tool", content=content, tool_call_id=tool_call_id)
        self.messages.append(message)
        return message

    def to_api_messages(self) -> list[dict[str, Any]]:
        """导出供 chat.completions.create(messages=...) 使用的历史。"""
        return [m.to_dict() for m in self.messages]

    def clear(self) -> None:
        self.messages.clear()

    def __len__(self) -> int:
        return len(self.messages)
