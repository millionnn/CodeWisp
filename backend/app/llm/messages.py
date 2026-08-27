"""对话消息与会话历史（当前版本的最小实现）。

仅支持 system / user / assistant，以及内存中的追加式历史列表。
复杂的上下文管理留给后续版本。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

Role = Literal["system", "user", "assistant"]

ALLOWED_ROLES: frozenset[str] = frozenset({"system", "user", "assistant"})


@dataclass(frozen=True)
class Message:
    """单条聊天消息。"""

    role: Role
    content: str

    def __post_init__(self) -> None:
        if self.role not in ALLOWED_ROLES:
            raise ValueError(f"不支持的角色: {self.role!r}")
        if not isinstance(self.content, str):
            raise TypeError("content 必须是字符串")

    def to_dict(self) -> dict[str, str]:
        """序列化为 OpenAI 兼容的 chat message 结构。"""
        return {"role": self.role, "content": self.content}


@dataclass
class Conversation:
    """内存中的多轮对话历史。

    故意保持简单：仅追加消息列表。
    当前版本不做截断、摘要或 token 预算。
    """

    messages: list[Message] = field(default_factory=list)

    def add(self, role: Role, content: str) -> Message:
        """追加一条消息并返回该消息。"""
        message = Message(role=role, content=content)
        self.messages.append(message)
        return message

    def add_user(self, content: str) -> Message:
        return self.add("user", content)

    def add_assistant(self, content: str) -> Message:
        return self.add("assistant", content)

    def add_system(self, content: str) -> Message:
        return self.add("system", content)

    def to_api_messages(self) -> list[dict[str, str]]:
        """导出供 chat.completions.create(messages=...) 使用的历史。"""
        return [m.to_dict() for m in self.messages]

    def clear(self) -> None:
        self.messages.clear()

    def __len__(self) -> int:
        return len(self.messages)
