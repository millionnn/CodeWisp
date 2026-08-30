"""V0.6 Phase 2-E：Session Resume / 跨进程续跑。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.app.agent.state import AgentStatus
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.persistence.agent_run_repository import AgentRunRepository
from backend.app.persistence.store import SqliteStore
from backend.app.services.agent_service import AgentService
from backend.app.session.errors import SessionNotFoundError
from backend.app.session.service import SessionService


class ScriptedLLMClient(LLMClient):
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.config = LLMConfig(api_key="fake", base_url="http://localhost", model="fake")
        self._client = None  # type: ignore[assignment]
        self._queue = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        conversation: Conversation,
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        self.calls.append({"messages": conversation.to_api_messages(), "tools": tools})
        if not self._queue:
            raise LLMRequestError("无更多脚本响应")
        return self._queue.pop(0)


def test_resume_session_loads_conversation_and_runs(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    store = SqliteStore(tmp_path / "a.db")
    store.connect()

    sessions = SessionService(store)
    session = sessions.create_session(title="resume-demo", workspace=ws)
    agent = AgentService(
        store,
        llm=ScriptedLLMClient(
            [
                LLMResponse(
                    content=None,
                    tool_calls=(
                        ToolCall(
                            id="c1",
                            name="calculator",
                            arguments={"expression": "1+2"},
                            arguments_raw='{"expression":"1+2"}',
                        ),
                    ),
                ),
                LLMResponse(content="3", tool_calls=()),
            ]
        ),
    )
    result = agent.run(session.session_id, "1+2?")

    resumed = sessions.resume_session(session.session_id)
    assert resumed.session_id == session.session_id
    assert resumed.workspace == str(ws.resolve())
    assert resumed.has_history is True
    assert resumed.message_count >= 4  # system,user,assistant+tool...,assistant
    assert resumed.run_count == 1
    assert resumed.latest_run is not None
    assert resumed.latest_run.agent_run_id == result.run.agent_run_id
    assert resumed.latest_run.final_answer == "3"
    assert any(m.role == "tool" for m in resumed.conversation.messages)

    via_agent = agent.resume(session.session_id)
    assert via_agent.run_count == 1


def test_process_restart_resume_then_continue(tmp_path: Path) -> None:
    """Process1 执行 → 关库 → Process2 resume → continue，LLM 看到完整历史。"""
    ws = tmp_path / "proj"
    ws.mkdir()
    db_path = tmp_path / "codewisp.db"

    # --- Process 1 ---
    store1 = SqliteStore(db_path)
    store1.connect()
    sessions1 = SessionService(store1)
    session = sessions1.create_session(
        title="long-lived",
        workspace=ws,
        provider_id="deepseek",
        model_id="deepseek-chat",
    )
    sid = session.session_id
    agent1 = AgentService(
        store1,
        llm=ScriptedLLMClient(
            [LLMResponse(content="第一轮完成", tool_calls=(), finish_reason="stop")]
        ),
    )
    agent1.run(sid, "记住苹果")
    store1.close()

    # --- Process 2 ---
    store2 = SqliteStore(db_path)
    store2.connect()
    agent2 = AgentService(
        store2,
        llm=ScriptedLLMClient(
            [LLMResponse(content="你说的是苹果", tool_calls=(), finish_reason="stop")]
        ),
    )
    resumed = agent2.resume(sid)
    assert resumed.session.title == "long-lived"
    assert resumed.provider_id == "deepseek"
    assert any(m.content == "记住苹果" for m in resumed.conversation.messages)
    assert sum(1 for m in resumed.conversation.messages if m.role == "system") == 1

    result2 = agent2.continue_session(sid, "我刚才说了什么？")
    assert result2.state.status == AgentStatus.COMPLETED
    assert result2.run.final_answer == "你说的是苹果"

    # 续跑时 LLM 输入包含第一轮 user/assistant
    second_msgs = agent2._llm.calls[0]["messages"]  # type: ignore[union-attr]
    contents = [m.get("content") for m in second_msgs]
    assert "记住苹果" in contents
    assert "第一轮完成" in contents
    assert contents.count("记住苹果") == 1

    # 仍只有一条 system
    final = agent2.resume(sid)
    assert sum(1 for m in final.conversation.messages if m.role == "system") == 1
    assert final.run_count == 2
    assert [r.final_answer for r in final.runs] == ["第一轮完成", "你说的是苹果"]


def test_resume_does_not_duplicate_system_message(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    store = SqliteStore(tmp_path / "sys.db")
    store.connect()
    sessions = SessionService(store)
    session = sessions.create_session(title="sys", workspace=ws)
    agent = AgentService(
        store,
        llm=ScriptedLLMClient(
            [
                LLMResponse(content="a", tool_calls=()),
                LLMResponse(content="b", tool_calls=()),
                LLMResponse(content="c", tool_calls=()),
            ]
        ),
    )
    agent.run(session.session_id, "u1")
    agent.run(session.session_id, "u2")
    agent.continue_session(session.session_id, "u3")

    msgs = sessions.load_conversation(session.session_id).messages
    assert sum(1 for m in msgs if m.role == "system") == 1
    assert [m.content for m in msgs if m.role == "user"] == ["u1", "u2", "u3"]


def test_resume_isolation_between_sessions(tmp_path: Path) -> None:
    ws_a = tmp_path / "a"
    ws_b = tmp_path / "b"
    ws_a.mkdir()
    ws_b.mkdir()
    store = SqliteStore(tmp_path / "iso.db")
    store.connect()
    sessions = SessionService(store)
    sa = sessions.create_session(title="A", workspace=ws_a)
    sb = sessions.create_session(title="B", workspace=ws_b)

    agent = AgentService(
        store,
        llm=ScriptedLLMClient(
            [
                LLMResponse(content="from-a", tool_calls=()),
                LLMResponse(content="from-b", tool_calls=()),
            ]
        ),
    )
    agent.run(sa.session_id, "msg-a")
    agent.run(sb.session_id, "msg-b")

    ra = sessions.resume_session(sa.session_id)
    rb = sessions.resume_session(sb.session_id)
    assert ra.workspace != rb.workspace
    assert any(m.content == "msg-a" for m in ra.conversation.messages)
    assert all(m.content != "msg-b" for m in ra.conversation.messages)
    assert any(m.content == "msg-b" for m in rb.conversation.messages)
    assert all(m.content != "msg-a" for m in rb.conversation.messages)


def test_resume_unknown_session(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "x.db")
    store.connect()
    with pytest.raises(SessionNotFoundError):
        SessionService(store).resume_session("ses_missing")


def test_resume_restores_step_and_tool_call_ids(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    db_path = tmp_path / "ids.db"

    store = SqliteStore(db_path)
    store.connect()
    sessions = SessionService(store)
    session = sessions.create_session(title="ids", workspace=ws)
    agent = AgentService(
        store,
        llm=ScriptedLLMClient(
            [
                LLMResponse(
                    content=None,
                    tool_calls=(
                        ToolCall(
                            id="call_edit",
                            name="calculator",
                            arguments={"expression": "9"},
                            arguments_raw='{"expression":"9"}',
                        ),
                    ),
                ),
                LLMResponse(content="nine", tool_calls=()),
            ]
        ),
    )
    result = agent.run(session.session_id, "calc")
    run_id = result.run.agent_run_id
    step_ids = [s.step_id for s in result.steps]
    store.close()

    store2 = SqliteStore(db_path)
    store2.connect()
    resumed = SessionService(store2).resume_session(session.session_id)
    runs = AgentRunRepository(store2)
    steps = runs.list_steps(run_id)
    tools = runs.list_tool_calls(agent_run_id=run_id)

    assert resumed.latest_run is not None
    assert resumed.latest_run.agent_run_id == run_id
    assert [s.step_id for s in steps] == step_ids
    assert tools[0].tool_call_id == "call_edit"
    assert tools[0].step_id in step_ids
