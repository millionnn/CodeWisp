"""消息与会话历史相关测试。"""

from __future__ import annotations

import pytest

from backend.app.llm.messages import Conversation, Message


def test_message_creation() -> None:
    msg = Message(role="user", content="hello")
    assert msg.role == "user"
    assert msg.content == "hello"
    assert msg.to_dict() == {"role": "user", "content": "hello"}


def test_message_rejects_invalid_role() -> None:
    with pytest.raises(ValueError, match="不支持的角色"):
        Message(role="tool", content="x")  # type: ignore[arg-type]


def test_conversation_history_order() -> None:
    conv = Conversation()
    conv.add_system("你是助手。")
    conv.add_user("什么是 BST？")
    conv.add_assistant("二叉搜索树……")

    assert len(conv) == 3
    assert conv.to_api_messages() == [
        {"role": "system", "content": "你是助手。"},
        {"role": "user", "content": "什么是 BST？"},
        {"role": "assistant", "content": "二叉搜索树……"},
    ]


def test_conversation_clear() -> None:
    conv = Conversation()
    conv.add_user("hi")
    conv.clear()
    assert len(conv) == 0
    assert conv.to_api_messages() == []
