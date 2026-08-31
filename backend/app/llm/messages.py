"""对话消息与会话历史。

支持 system / user / assistant / tool，以及 assistant 的 tool_calls。
上下文压缩由 ContextManager 在 AgentLoop 侧生成「模型视图」完成；
本模块的 Conversation 仍为 durable 追加式历史（不在此删除消息）。

``to_dict`` / ``to_api_messages``：OpenAI 兼容 wire 格式（可能丢失 parse_error）。
``to_persistence_dict`` / ``from_persistence_dict``：完整领域 round-trip（V0.6）。
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from backend.app.llm.response import ToolCall
from backend.app.session.ids import new_message_id

Role = Literal["system", "user", "assistant", "tool"]

ALLOWED_ROLES: frozenset[str] = frozenset({"system", "user", "assistant", "tool"})


@dataclass(frozen=True)
class Message:
    """单条聊天消息（可含 tool_calls 或 tool_call_id）。

    可选持久化元数据（message_id / session_id / …）不进入 ``to_dict`` wire 格式。
    """

    role: Role
    content: str | None = ""
    tool_calls: tuple[ToolCall, ...] = ()
    tool_call_id: str | None = None
    message_id: str | None = None
    session_id: str | None = None
    agent_run_id: str | None = None
    step_id: str | None = None
    seq: int | None = None
    created_at: str | None = None

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

#将消息序列化，用于持久化
    def to_persistence_dict(self) -> dict[str, Any]:
        """完整领域序列化（含元数据与 ToolCall 全字段）。"""
        return {
            "message_id": self.message_id,
            "session_id": self.session_id,
            "agent_run_id": self.agent_run_id,
            "step_id": self.step_id,
            "seq": self.seq,
            "role": self.role,
            "content": self.content,
            "tool_call_id": self.tool_call_id,
            "tool_calls": [tc.to_persistence_dict() for tc in self.tool_calls],
            "created_at": self.created_at,
        }

#将持久化数据反序列化，用于持久化 round-trip
    @classmethod
    def from_persistence_dict(cls, data: dict[str, Any]) -> Message:
        if not isinstance(data, dict):
            raise TypeError("Message.from_persistence_dict 需要 dict")
        role = data.get("role")
        if role not in ALLOWED_ROLES:
            raise ValueError(f"不支持的角色: {role!r}")
        content = data.get("content", "")
        if content is not None and not isinstance(content, str):
            raise TypeError("content 必须是字符串或 None")
        raw_calls = data.get("tool_calls") or []
        if not isinstance(raw_calls, list):
            raise ValueError("tool_calls 必须是 list")
        tool_calls = tuple(
            ToolCall.from_persistence_dict(item).with_stable_id() for item in raw_calls
        )
        tool_call_id = data.get("tool_call_id")
        if tool_call_id is not None and not isinstance(tool_call_id, str):
            raise ValueError("tool_call_id 必须是字符串或 None")
        seq = data.get("seq")
        if seq is not None and (not isinstance(seq, int) or isinstance(seq, bool)):
            raise ValueError("seq 必须是 int 或 None")
        message_id = data.get("message_id")
        if message_id is not None and not isinstance(message_id, str):
            raise ValueError("message_id 必须是字符串或 None")
        return cls(
            role=role,  # type: ignore[arg-type]
            content=content,
            tool_calls=tool_calls,
            tool_call_id=tool_call_id,
            message_id=message_id,
            session_id=_optional_meta_str(data, "session_id"),
            agent_run_id=_optional_meta_str(data, "agent_run_id"),
            step_id=_optional_meta_str(data, "step_id"),
            seq=seq,
            created_at=_optional_meta_str(data, "created_at"),
        )

#返回持久化好的元数据
    def with_persistence_meta(
        self,
        *,
        message_id: str | None = None,
        session_id: str | None = None,
        agent_run_id: str | None = None,
        step_id: str | None = None,
        seq: int | None = None,
        created_at: str | None = None,
        assign_message_id: bool = False,
    ) -> Message:
        """返回带持久化元数据的新 Message（frozen 替换）。"""
        mid = message_id if message_id is not None else self.message_id
        if assign_message_id and not mid:
            mid = new_message_id()
        return Message(
            role=self.role,
            content=self.content,
            tool_calls=tuple(tc.with_stable_id() for tc in self.tool_calls),
            tool_call_id=self.tool_call_id,
            message_id=mid,
            session_id=session_id if session_id is not None else self.session_id,
            agent_run_id=agent_run_id if agent_run_id is not None else self.agent_run_id,
            step_id=step_id if step_id is not None else self.step_id,
            seq=seq if seq is not None else self.seq,
            created_at=created_at if created_at is not None else self.created_at,
        )

#返回持久化好的元数据
def _optional_meta_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"{key} 必须是字符串或 None")
    return value


def _tool_arguments_for_api(tc: ToolCall) -> str:
    if tc.arguments_raw is not None:
        return tc.arguments_raw
    return json.dumps(tc.arguments, ensure_ascii=False)


@dataclass
class Conversation:
    """内存中的多轮对话历史（追加式；压缩不改写本列表）。"""

    messages: list[Message] = field(default_factory=list)

    def add(self, role: Role, content: str | None) -> Message:
        """追加一条简单文本消息。"""
        message = Message(role=role, content=content)#创建一条消息
        self.messages.append(message)#将消息添加到对话历史中
        return message

    def add_user(self, content: str) -> Message:
        return self.add("user", content)#添加一条用户消息

    def add_assistant(self, content: str | None) -> Message:
        return self.add("assistant", content)#添加一条助手消息

    def add_system(self, content: str) -> Message:
        return self.add("system", content)#添加一条系统消息

    def add_assistant_tool_calls(
        self,
        content: str | None,
        tool_calls: tuple[ToolCall, ...] | list[ToolCall],
    ) -> Message:
        """追加带 tool_calls 的 assistant 消息。"""
        calls = tuple(tc.with_stable_id() for tc in tool_calls)#给工具调用分配一个稳定的id
        message = Message(role="assistant", content=content, tool_calls=calls)
        self.messages.append(message)#将消息添加到对话历史中
        return message

    def add_tool_result(self, tool_call_id: str, content: str) -> Message:
        """追加 tool observation（工具执行结果）。"""
        message = Message(role="tool", content=content, tool_call_id=tool_call_id)#创建一条工具消息
        self.messages.append(message)#将消息添加到对话历史中
        return message

    def to_api_messages(self) -> list[dict[str, Any]]:
        """导出供 chat.completions.create(messages=...) 使用的历史。"""
        return [m.to_dict() for m in self.messages]#将消息序列化为OpenAI兼容的chat message结构

    def to_dict(self) -> dict[str, Any]:
        """持久化序列化：有序 messages 完整领域表示。"""
        return {"messages": [m.to_persistence_dict() for m in self.messages]}#将消息序列化为持久化数据

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Conversation:
        if not isinstance(data, dict):
            raise TypeError("Conversation.from_dict 需要 dict")
        raw_messages = data.get("messages")
        if not isinstance(raw_messages, list):
            raise ValueError("messages 必须是 list")
        conv = cls()
        for item in raw_messages:
            conv.messages.append(Message.from_persistence_dict(item))
        return conv

    def clear(self) -> None:
        self.messages.clear()

    def __len__(self) -> int:
        return len(self.messages)
