"""V0.6 Phase 2-C：Repository CRUD / isolation / restart / round-trip。"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.llm.messages import Message
from backend.app.llm.response import ToolCall
from backend.app.persistence.agent_run_repository import AgentRunRepository
from backend.app.persistence.conversation_repository import ConversationRepository
from backend.app.persistence.errors import ConflictError, NotFoundError
from backend.app.persistence.session_repository import SessionRepository
from backend.app.persistence.store import SqliteStore
from backend.app.session.models import AgentRun, AgentStep, Session
from backend.app.tools.result import ToolResult


@pytest.fixture
def store() -> SqliteStore:
    s = SqliteStore(":memory:")
    s.connect()
    return s


def _create_session(
    sessions: SessionRepository,
    *,
    title: str = "t",
    workspace: str = "/ws-a",
    provider_id: str = "deepseek",
    model_id: str = "deepseek-chat",
) -> Session:
    return sessions.create(
        Session.create(
            title=title,
            workspace=workspace,
            provider_id=provider_id,
            model_id=model_id,
        )
    )


def test_session_crud(store: SqliteStore) -> None:
    sessions = SessionRepository(store)
    created = _create_session(sessions, title="Fix auth", workspace="/project-a")
    got = sessions.get(created.session_id)
    assert got.title == "Fix auth"
    assert got.workspace == "/project-a"
    assert got.provider_id == "deepseek"

    renamed = sessions.rename(created.session_id, "Auth v2")
    assert renamed.title == "Auth v2"
    assert sessions.get(created.session_id).title == "Auth v2"

    listed = sessions.list()
    assert any(s.session_id == created.session_id for s in listed)

    sessions.delete(created.session_id)
    with pytest.raises(NotFoundError):
        sessions.get(created.session_id)


def test_session_not_found_and_conflict(store: SqliteStore) -> None:
    sessions = SessionRepository(store)
    with pytest.raises(NotFoundError):
        sessions.get("ses_missing")

    s = _create_session(sessions)
    with pytest.raises(ConflictError):
        sessions.create(s)


def test_conversation_append_list_roundtrip_tool_fields(store: SqliteStore) -> None:
    sessions = SessionRepository(store)
    conv_repo = ConversationRepository(store)
    session = _create_session(sessions)

    conv_repo.append_message(session.session_id, Message(role="system", content="sys"))
    conv_repo.append_message(session.session_id, Message(role="user", content="edit"))

    tc = ToolCall(
        id="call_x",
        name="edit_file",
        arguments={"path": "a.py"},
        arguments_raw='{"path":"a.py"}',
        parse_error=None,
    )
    conv_repo.append_message(
        session.session_id,
        Message(role="assistant", content=None, tool_calls=(tc,)),
    )
    obs = json.dumps(ToolResult(success=True, output="ok").to_dict())
    conv_repo.append_message(
        session.session_id,
        Message(role="tool", content=obs, tool_call_id="call_x"),
    )

    messages = conv_repo.list_messages(session.session_id)
    assert [m.role for m in messages] == ["system", "user", "assistant", "tool"]
    assert messages[0].seq == 1 and messages[3].seq == 4
    assert messages[2].tool_calls[0].arguments_raw == '{"path":"a.py"}'
    assert messages[3].tool_call_id == "call_x"

    loaded = conv_repo.load_conversation(session.session_id)
    assert len(loaded) == 4


def test_agent_run_step_tool_call_graph(store: SqliteStore) -> None:
    sessions = SessionRepository(store)
    runs = AgentRunRepository(store)
    session = _create_session(
        sessions, provider_id="openai", model_id="gpt-test", workspace="/b"
    )

    run = runs.create_run(
        AgentRun.create(
            session_id=session.session_id,
            provider_id=session.provider_id,
            model_id=session.model_id,
            status="running",
        )
    )
    assert run.provider_id == "openai"
    assert run.model_id == "gpt-test"

    step = runs.add_step(
        AgentStep.create(
            agent_run_id=run.agent_run_id,
            session_id=session.session_id,
            step_index=1,
            status="running",
        )
    )
    assert step.step_id.startswith("step_")

    tc = ToolCall(
        id="",
        name="edit_file",
        arguments={"path": "x.py", "old_text": "1", "new_text": "2"},
        arguments_raw=None,
        parse_error=None,
    )
    result = ToolResult(
        success=True,
        output="updated",
        metadata={"path": "x.py"},
    )
    persisted = runs.add_tool_call(
        session_id=session.session_id,
        agent_run_id=run.agent_run_id,
        step_id=step.step_id,
        tool_call=tc,
        result=result,
    )
    assert persisted.tool_call_id.startswith("tc_")
    assert persisted.result is not None
    assert persisted.result.metadata["path"] == "x.py"

    runs.complete_step(step.step_id, status="completed")
    completed = runs.complete_run(
        run.agent_run_id,
        status="completed",
        termination_reason="completed",
        final_answer="done",
    )
    assert completed.termination_reason == "completed"
    assert completed.provider_id == "openai"

    assert len(runs.list_steps(run.agent_run_id)) == 1
    assert len(runs.list_tool_calls(step_id=step.step_id)) == 1
    assert runs.get_tool_call(persisted.tool_call_id).tool_name == "edit_file"


def test_session_isolation_messages_and_workspace(store: SqliteStore) -> None:
    sessions = SessionRepository(store)
    conv = ConversationRepository(store)

    a = _create_session(sessions, title="A", workspace="/project-a")
    b = _create_session(
        sessions,
        title="B",
        workspace="/project-b",
        provider_id="openai",
        model_id="gpt-x",
    )

    conv.append_message(a.session_id, Message(role="user", content="msg-a"))
    conv.append_message(b.session_id, Message(role="user", content="msg-b"))

    msgs_a = conv.list_messages(a.session_id)
    msgs_b = conv.list_messages(b.session_id)
    assert [m.content for m in msgs_a] == ["msg-a"]
    assert [m.content for m in msgs_b] == ["msg-b"]
    assert sessions.get(a.session_id).workspace != sessions.get(b.session_id).workspace


def test_restart_persistence_file_db(tmp_path: Path) -> None:
    db_path = tmp_path / "repos.db"

    with SqliteStore(db_path) as store:
        sessions = SessionRepository(store)
        conv = ConversationRepository(store)
        runs = AgentRunRepository(store)

        session = _create_session(sessions, title="persist")
        conv.append_message(session.session_id, Message(role="user", content="hello"))
        run = runs.create_run(
            AgentRun.create(
                session_id=session.session_id,
                provider_id=session.provider_id,
                model_id=session.model_id,
            )
        )
        step = runs.add_step(
            AgentStep.create(
                agent_run_id=run.agent_run_id,
                session_id=session.session_id,
                step_index=1,
            )
        )
        runs.add_tool_call(
            session_id=session.session_id,
            agent_run_id=run.agent_run_id,
            step_id=step.step_id,
            tool_call=ToolCall(id="call_1", name="read_file", arguments={"path": "a"}),
            result=ToolResult(success=True, output="data"),
        )
        sid, rid, step_id = session.session_id, run.agent_run_id, step.step_id

    # Process 2
    with SqliteStore(db_path) as store:
        sessions = SessionRepository(store)
        conv = ConversationRepository(store)
        runs = AgentRunRepository(store)

        assert sessions.get(sid).title == "persist"
        assert conv.list_messages(sid)[0].content == "hello"
        assert runs.get_run(rid).model_id == "deepseek-chat"
        assert runs.get_step(step_id).step_index == 1
        assert runs.list_tool_calls(agent_run_id=rid)[0].tool_name == "read_file"


def test_delete_session_cascades(store: SqliteStore) -> None:
    sessions = SessionRepository(store)
    conv = ConversationRepository(store)
    runs = AgentRunRepository(store)

    session = _create_session(sessions)
    run = runs.create_run(
        AgentRun.create(
            session_id=session.session_id,
            provider_id="deepseek",
            model_id="deepseek-chat",
        )
    )
    step = runs.add_step(
        AgentStep.create(
            agent_run_id=run.agent_run_id,
            session_id=session.session_id,
            step_index=1,
        )
    )
    conv.append_message(
        session.session_id,
        Message(
            role="user",
            content="x",
            agent_run_id=run.agent_run_id,
            step_id=step.step_id,
        ),
    )
    runs.add_tool_call(
        session_id=session.session_id,
        agent_run_id=run.agent_run_id,
        step_id=step.step_id,
        tool_call=ToolCall(id="tc_del", name="list_files", arguments={}),
    )

    sessions.delete(session.session_id)
    with pytest.raises(NotFoundError):
        runs.get_run(run.agent_run_id)
    assert store.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
    assert store.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0] == 0
