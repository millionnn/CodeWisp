"""V0.6 Phase 2-A：领域对象持久化序列化 / round-trip 测试。"""

from __future__ import annotations

import json

import pytest

from backend.app.agent.events import AgentEvent
from backend.app.llm.messages import Conversation, Message
from backend.app.llm.response import ToolCall
from backend.app.session.ids import new_id, new_session_id, new_tool_call_id
from backend.app.session.models import AgentRun, AgentStep, Session
from backend.app.tools.result import ToolResult


def test_message_create_serialize_deserialize_roundtrip() -> None:
    msg = Message(
        role="user",
        content="修复测试",
        message_id="msg_1",
        session_id="ses_1",
        agent_run_id="run_1",
        step_id=None,
        seq=2,
        created_at="2026-08-30T00:00:00Z",
    )
    payload = msg.to_persistence_dict()
    restored = Message.from_persistence_dict(payload)
    assert restored == msg
    # wire 格式不含 persistence 元数据
    assert msg.to_dict() == {"role": "user", "content": "修复测试"}


def test_tool_call_normal_roundtrip() -> None:
    tc = ToolCall(
        id="call_abc",
        name="edit_file",
        arguments={"path": "a.py", "old_text": "x", "new_text": "y"},
        arguments_raw='{"path":"a.py","old_text":"x","new_text":"y"}',
        parse_error=None,
    )
    restored = ToolCall.from_persistence_dict(tc.to_persistence_dict())
    assert restored == tc


def test_tool_call_arguments_raw_and_parse_error_roundtrip() -> None:
    tc = ToolCall(
        id="call_bad",
        name="run_command",
        arguments={},
        arguments_raw="{not-json",
        parse_error="Expecting property name",
    )
    restored = ToolCall.from_persistence_dict(tc.to_persistence_dict())
    assert restored.arguments_raw == "{not-json"
    assert restored.parse_error == "Expecting property name"
    assert restored == tc


def test_tool_call_empty_id_gets_stable_tc_uuid() -> None:
    tc = ToolCall(id="", name="read_file", arguments={"path": "a.py"})
    stable = tc.with_stable_id()
    assert stable.id.startswith("tc_")
    assert len(stable.id) == len("tc_") + 32
    # from_persistence 也会补齐
    restored = ToolCall.from_persistence_dict(
        {"id": "", "name": "read_file", "arguments": {"path": "a.py"}}
    )
    assert restored.id.startswith("tc_")
    assert restored.name == "read_file"


def test_tool_call_rejects_call_step_style_as_generator() -> None:
    # 我们生成的是 tc_<uuid>，不是 call_step_N
    a = new_tool_call_id()
    b = new_tool_call_id()
    assert a != b
    assert a.startswith("tc_")
    assert "call_step" not in a


def test_tool_result_roundtrip() -> None:
    result = ToolResult(
        success=True,
        output={"replacements": 1},
        error=None,
        metadata={"path": "app/x.py", "tool_name": "edit_file"},
    )
    restored = ToolResult.from_dict(result.to_dict())
    assert restored == result


def test_conversation_multi_message_ordering_and_tool_roundtrip() -> None:
    conv = Conversation()
    conv.add_system("sys")
    conv.add_user("请编辑")
    tc = ToolCall(
        id="call_1",
        name="edit_file",
        arguments={"path": "f.py", "old_text": "a", "new_text": "b"},
        arguments_raw='{"path":"f.py"}',
        parse_error=None,
    )
    conv.add_assistant_tool_calls("thinking", (tc,))
    observation = json.dumps(
        ToolResult(success=True, output="ok", metadata={"path": "f.py"}).to_dict(),
        ensure_ascii=False,
    )
    conv.add_tool_result("call_1", observation)
    conv.add_assistant("完成")

    payload = conv.to_dict()
    restored = Conversation.from_dict(payload)

    assert len(restored) == 5
    assert [m.role for m in restored.messages] == [
        "system",
        "user",
        "assistant",
        "tool",
        "assistant",
    ]
    assert restored.messages[2].tool_calls[0].arguments_raw == '{"path":"f.py"}'
    assert restored.messages[3].tool_call_id == "call_1"
    assert json.loads(restored.messages[3].content or "")["success"] is True
    # API wire 仍可用
    assert len(restored.to_api_messages()) == 5


def test_agent_run_provider_model_snapshot_roundtrip() -> None:
    run = AgentRun.create(
        session_id="ses_x",
        provider_id="deepseek",
        model_id="deepseek-chat",
        status="completed",
        termination_reason="completed",
        max_steps=15,
        final_answer="done",
        error=None,
        created_at="t0",
        completed_at="t1",
        agent_run_id="run_fixed",
    )
    restored = AgentRun.from_dict(run.to_dict())
    assert restored == run
    assert restored.provider_id == "deepseek"
    assert restored.model_id == "deepseek-chat"
    assert restored.termination_reason == "completed"


def test_agent_step_stable_id_and_association_roundtrip() -> None:
    step = AgentStep.create(
        agent_run_id="run_1",
        session_id="ses_1",
        step_index=2,
        status="completed",
        step_id="step_fixed",
        created_at="t0",
        completed_at="t1",
    )
    restored = AgentStep.from_dict(step.to_dict())
    assert restored == step
    assert restored.step_id == "step_fixed"
    assert restored.step_index == 2
    assert restored.agent_run_id == "run_1"

    auto = AgentStep.create(
        agent_run_id="run_1", session_id="ses_1", step_index=1
    )
    assert auto.step_id.startswith("step_")
    assert auto.step_id != "1"


def test_agent_step_rejects_non_positive_index() -> None:
    with pytest.raises(ValueError, match="step_index"):
        AgentStep.create(agent_run_id="r", session_id="s", step_index=0)


def test_session_roundtrip() -> None:
    session = Session.create(
        title="Fix auth",
        workspace="/project-a",
        provider_id="openai",
        model_id="gpt-test",
        session_id="ses_fixed",
        created_at="t0",
        updated_at="t0",
    )
    restored = Session.from_dict(session.to_dict())
    assert restored == session


def test_agent_event_roundtrip_for_future_adapter() -> None:
    event = AgentEvent(
        event_type="tool_completed",
        step=2,
        timestamp=1.5,
        tool_name="edit_file",
        metadata={"tool_call_id": "tc_1", "success": True},
    )
    restored = AgentEvent.from_dict(event.to_dict())
    assert restored.event_type == event.event_type
    assert restored.step == 2
    assert restored.metadata["tool_call_id"] == "tc_1"


def test_combined_session_run_step_message_toolcall_observation_graph() -> None:
    """Session → Run → Step → Message → ToolCall → Observation 无损表达。"""
    session = Session.create(
        title="Demo",
        workspace="/ws-a",
        provider_id="deepseek",
        model_id="deepseek-chat",
    )
    run = AgentRun.create(
        session_id=session.session_id,
        provider_id=session.provider_id,
        model_id=session.model_id,
        status="completed",
        termination_reason="completed",
        final_answer="已修复",
    )
    step = AgentStep.create(
        agent_run_id=run.agent_run_id,
        session_id=session.session_id,
        step_index=1,
    )
    tc = ToolCall(
        id="",
        name="edit_file",
        arguments={"path": "app/x.py", "old_text": "1", "new_text": "2"},
        arguments_raw=None,
        parse_error=None,
    ).with_stable_id()
    observation = ToolResult(
        success=True,
        output="updated",
        metadata={"path": "app/x.py"},
    )
    assistant = Message(
        role="assistant",
        content=None,
        tool_calls=(tc,),
        message_id=new_id("msg"),
        session_id=session.session_id,
        agent_run_id=run.agent_run_id,
        step_id=step.step_id,
        seq=1,
        created_at="t1",
    )
    tool_msg = Message(
        role="tool",
        content=json.dumps(observation.to_dict(), ensure_ascii=False),
        tool_call_id=tc.id,
        message_id=new_id("msg"),
        session_id=session.session_id,
        agent_run_id=run.agent_run_id,
        step_id=step.step_id,
        seq=2,
        created_at="t2",
    )

    graph = {
        "session": session.to_dict(),
        "run": run.to_dict(),
        "step": step.to_dict(),
        "messages": [
            assistant.to_persistence_dict(),
            tool_msg.to_persistence_dict(),
        ],
        "observation": observation.to_dict(),
    }
    # 模拟「可写入 SQLite 的 primitive / JSON」再还原
    blob = json.loads(json.dumps(graph))

    s2 = Session.from_dict(blob["session"])
    r2 = AgentRun.from_dict(blob["run"])
    st2 = AgentStep.from_dict(blob["step"])
    m_as = Message.from_persistence_dict(blob["messages"][0])
    m_tool = Message.from_persistence_dict(blob["messages"][1])
    obs2 = ToolResult.from_dict(blob["observation"])

    assert s2.session_id == r2.session_id == st2.session_id == m_as.session_id
    assert r2.agent_run_id == st2.agent_run_id == m_as.agent_run_id
    assert st2.step_id == m_as.step_id == m_tool.step_id
    assert m_as.tool_calls[0].id == m_tool.tool_call_id
    assert m_as.tool_calls[0].id.startswith("tc_")
    assert m_as.tool_calls[0].name == "edit_file"
    assert obs2.metadata["path"] == "app/x.py"
    assert r2.provider_id == "deepseek" and r2.model_id == "deepseek-chat"


def test_new_session_id_unique() -> None:
    assert new_session_id() != new_session_id()
