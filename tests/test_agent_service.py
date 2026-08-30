"""V0.6 Phase 2-D：AgentService 持久化编排测试。"""

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
from backend.app.persistence.conversation_repository import ConversationRepository
from backend.app.persistence.store import SqliteStore
from backend.app.services.agent_service import AgentService
from backend.app.session.errors import (
    InvalidMessageError,
    InvalidWorkspaceError,
    SessionBusyError,
    SessionNotFoundError,
)
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


@pytest.fixture
def db_workspace(tmp_path: Path) -> tuple[SqliteStore, Path]:
    ws = tmp_path / "project"
    ws.mkdir()
    store = SqliteStore(tmp_path / "codewisp.db")
    store.connect()
    return store, ws


def test_agent_service_simple_completion_persists_run_and_messages(
    db_workspace: tuple[SqliteStore, Path],
) -> None:
    store, ws = db_workspace
    sessions = SessionService(store)
    session = sessions.create_session(
        title="demo",
        workspace=ws,
        provider_id="deepseek",
        model_id="deepseek-chat",
    )

    llm = ScriptedLLMClient(
        [LLMResponse(content="你好，任务完成。", tool_calls=(), finish_reason="stop")]
    )
    agent = AgentService(store, llm=llm, max_steps=5)

    result = agent.run(session.session_id, "打个招呼")
    assert result.state.status == AgentStatus.COMPLETED
    assert result.run.status == "completed"
    assert result.run.termination_reason == "completed"
    assert result.run.provider_id == "deepseek"
    assert result.run.model_id == "deepseek-chat"
    assert result.run.final_answer == "你好，任务完成。"
    assert len(result.steps) == 1
    assert result.steps[0].step_id.startswith("step_")

    conv = sessions.load_conversation(session.session_id)
    roles = [m.role for m in conv.messages]
    assert roles[0] == "system"
    assert "user" in roles and "assistant" in roles
    assert any(m.content == "打个招呼" for m in conv.messages)
    assert any(m.content == "你好，任务完成。" for m in conv.messages)


def test_agent_service_tool_trajectory_persists_tool_calls(
    db_workspace: tuple[SqliteStore, Path],
) -> None:
    store, ws = db_workspace
    sessions = SessionService(store)
    session = sessions.create_session(title="tools", workspace=ws)

    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_calc",
                        name="calculator",
                        arguments={"expression": "1+1"},
                        arguments_raw='{"expression":"1+1"}',
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="结果是 2", tool_calls=(), finish_reason="stop"),
        ]
    )
    agent = AgentService(store, llm=llm, max_steps=5)
    result = agent.run(session.session_id, "算 1+1")

    assert result.state.status == AgentStatus.COMPLETED
    assert len(result.steps) == 2

    runs = AgentRunRepository(store)
    tools = runs.list_tool_calls(agent_run_id=result.run.agent_run_id)
    assert len(tools) == 1
    assert tools[0].tool_name == "calculator"
    assert tools[0].tool_call_id == "call_calc"
    assert tools[0].result is not None
    assert tools[0].result.success is True

    conv = ConversationRepository(store).list_messages(session.session_id)
    assert any(m.role == "tool" and m.tool_call_id == "call_calc" for m in conv)
    tool_msg = next(m for m in conv if m.role == "tool")
    assert tool_msg.step_id == tools[0].step_id
    assert tool_msg.agent_run_id == result.run.agent_run_id


def test_agent_service_second_turn_reuses_history(
    db_workspace: tuple[SqliteStore, Path],
) -> None:
    store, ws = db_workspace
    sessions = SessionService(store)
    session = sessions.create_session(title="multi", workspace=ws)

    llm = ScriptedLLMClient(
        [
            LLMResponse(content="第一轮", tool_calls=(), finish_reason="stop"),
            LLMResponse(content="第二轮", tool_calls=(), finish_reason="stop"),
        ]
    )
    agent = AgentService(store, llm=llm, max_steps=5)
    agent.run(session.session_id, "第一问")
    agent.run(session.session_id, "第二问")

    conv = sessions.load_conversation(session.session_id)
    users = [m.content for m in conv.messages if m.role == "user"]
    assert users == ["第一问", "第二问"]
    # 第二轮 LLM 应看到历史
    assert len(llm.calls) == 2
    roles = [m["role"] for m in llm.calls[1]["messages"]]
    assert roles.count("user") >= 2


def test_agent_service_session_busy(
    db_workspace: tuple[SqliteStore, Path],
) -> None:
    store, ws = db_workspace
    sessions = SessionService(store)
    session = sessions.create_session(title="busy", workspace=ws)
    agent = AgentService(
        store,
        llm=ScriptedLLMClient(
            [LLMResponse(content="ok", tool_calls=(), finish_reason="stop")]
        ),
    )

    lock = agent._session_locks.setdefault(session.session_id, __import__("threading").Lock())
    assert lock.acquire(blocking=False)
    try:
        with pytest.raises(SessionBusyError):
            agent.run(session.session_id, "hello")
    finally:
        lock.release()


def test_agent_service_rejects_empty_message(
    db_workspace: tuple[SqliteStore, Path],
) -> None:
    store, ws = db_workspace
    sessions = SessionService(store)
    session = sessions.create_session(title="x", workspace=ws)
    agent = AgentService(
        store,
        llm=ScriptedLLMClient([]),
    )
    with pytest.raises(InvalidMessageError):
        agent.run(session.session_id, "   ")


def test_agent_service_invalid_session(
    db_workspace: tuple[SqliteStore, Path],
) -> None:
    store, _ws = db_workspace
    agent = AgentService(
        store,
        llm=ScriptedLLMClient([]),
    )
    with pytest.raises(SessionNotFoundError):
        agent.run("ses_missing", "hi")


def test_session_service_rejects_bad_workspace(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")
    store.connect()
    sessions = SessionService(store)
    with pytest.raises(InvalidWorkspaceError):
        sessions.create_session(title="x", workspace=tmp_path / "nope")


def test_agent_service_restart_keeps_trajectory(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    db_path = tmp_path / "agent.db"

    store = SqliteStore(db_path)
    store.connect()
    sessions = SessionService(store)
    session = sessions.create_session(title="restart", workspace=ws)
    sid = session.session_id

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
                            arguments={"expression": "2+2"},
                            arguments_raw='{"expression":"2+2"}',
                        ),
                    ),
                ),
                LLMResponse(content="4", tool_calls=()),
            ]
        ),
    )
    result = agent.run(sid, "2+2?")
    run_id = result.run.agent_run_id
    store.close()

    store2 = SqliteStore(db_path)
    store2.connect()
    sessions2 = SessionService(store2)
    runs = AgentRunRepository(store2)

    assert sessions2.get_session(sid).title == "restart"
    msgs = sessions2.load_conversation(sid).messages
    assert any(m.role == "tool" for m in msgs)
    assert runs.get_run(run_id).final_answer == "4"
    assert len(runs.list_steps(run_id)) == 2
    assert len(runs.list_tool_calls(agent_run_id=run_id)) == 1
