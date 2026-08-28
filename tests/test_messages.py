"""消息与会话历史相关测试。"""

from __future__ import annotations

import pytest

from backend.app.llm.messages import Conversation, Message
from backend.app.llm.response import ToolCall


def test_message_creation() -> None:
    msg = Message(role="user", content="hello")
    assert msg.role == "user"
    assert msg.content == "hello"
    assert msg.to_dict() == {"role": "user", "content": "hello"}


def test_message_rejects_invalid_role() -> None:
    with pytest.raises(ValueError, match="不支持的角色"):
        Message(role="foobar", content="x")  # type: ignore[arg-type]


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


def test_assistant_tool_calls_and_tool_result_roundtrip() -> None:
    conv = Conversation()
    tc = ToolCall(
        id="call_1",
        name="calculator",
        arguments={"expression": "1+1"},
        arguments_raw='{"expression":"1+1"}',
    )
    conv.add_assistant_tool_calls(None, (tc,))
    conv.add_tool_result("call_1", '{"success": true, "output": 2}')

    api = conv.to_api_messages()
    assert api[0]["role"] == "assistant"
    assert api[0]["tool_calls"][0]["function"]["name"] == "calculator"
    assert api[1] == {
        "role": "tool",
        "tool_call_id": "call_1",
        "content": '{"success": true, "output": 2}',
    }


def test_tool_message_requires_tool_call_id() -> None:
    with pytest.raises(ValueError, match="tool_call_id"):
        Message(role="tool", content="x")
