"""V0.9 Phase 3：Revert step/run、Permission、审计 Snapshot。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.agent.event_sink import RecordingEventSink
from backend.app.agent.state import AgentStatus
from backend.app.changes.errors import RevertError
from backend.app.changes.models import ChangeType
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.persistence.store import SqliteStore
from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.handler import ScriptedPermissionHandler
from backend.app.services.agent_service import AgentService
from backend.app.session.service import SessionService


class ScriptedLLMClient(LLMClient):
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.config = LLMConfig(api_key="fake", base_url="http://localhost", model="fake")
        self._client = None  # type: ignore[assignment]
        self._queue = list(responses)

    def chat(
        self,
        conversation: Conversation,
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        if not self._queue:
            raise LLMRequestError("无更多脚本响应")
        return self._queue.pop(0)


def _run_edit(tmp_path: Path) -> tuple[AgentService, Any, str, Path]:
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "calc.py").write_text("return a - b\n", encoding="utf-8")
    store = SqliteStore(tmp_path / "cw.db")
    store.connect()
    session = SessionService(store).create_session(title="r", workspace=ws)
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="tc_edit1",
                        name="edit_file",
                        arguments={
                            "path": "calc.py",
                            "old_text": "return a - b",
                            "new_text": "return a + b",
                        },
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="done", tool_calls=(), finish_reason="stop"),
        ]
    )
    agent = AgentService(store, llm=llm, max_steps=5)
    result = agent.run(session.session_id, "fix")
    assert result.state.status == AgentStatus.COMPLETED
    step_id = agent.list_run_file_changes(result.run.agent_run_id)[0].agent_step_id
    return agent, result, step_id, ws


def test_revert_step_restores_file_and_keeps_history(tmp_path: Path) -> None:
    agent, result, step_id, ws = _run_edit(tmp_path)
    assert (ws / "calc.py").read_text(encoding="utf-8") == "return a + b\n"

    sink = RecordingEventSink()
    report = agent.revert_step(step_id, event_sink=sink)
    assert report.ok
    assert report.denied is False
    assert report.safety_snapshot_id
    assert (ws / "calc.py").read_text(encoding="utf-8") == "return a - b\n"

    # 历史不变
    changes = agent.list_run_file_changes(result.run.agent_run_id)
    assert len(changes) == 1
    assert changes[0].change_type is ChangeType.MODIFIED
    before, after = agent.get_step_snapshots(step_id)
    assert before is not None and after is not None
    assert after.file_map()["calc.py"].content == "return a + b\n"

    # 审计 snapshot 存在
    safety = agent.get_snapshot(report.safety_snapshot_id)
    assert safety.reason == "pre_revert"
    types = [e.event_type for e in sink.events]
    assert "revert_started" in types
    assert "snapshot_created" in types
    assert "revert_completed" in types


def test_revert_step_permission_deny(tmp_path: Path) -> None:
    agent, _result, step_id, ws = _run_edit(tmp_path)
    handler = ScriptedPermissionHandler([PermissionDecision.DENY])
    report = agent.revert_step(step_id, permission_handler=handler)
    assert report.denied is True
    assert report.ok is False
    assert (ws / "calc.py").read_text(encoding="utf-8") == "return a + b\n"
    assert len(handler.requests) == 1
    assert handler.requests[0].tool_name == "revert_step"


def test_revert_step_permission_allow(tmp_path: Path) -> None:
    agent, _result, step_id, ws = _run_edit(tmp_path)
    handler = ScriptedPermissionHandler([PermissionDecision.ALLOW])
    report = agent.revert_step(step_id, permission_handler=handler)
    assert report.ok
    assert (ws / "calc.py").read_text(encoding="utf-8") == "return a - b\n"


def test_revert_run_multi_step(tmp_path: Path) -> None:
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "a.py").write_text("A0\n", encoding="utf-8")
    store = SqliteStore(tmp_path / "cw.db")
    store.connect()
    session = SessionService(store).create_session(title="multi", workspace=ws)
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="tc1",
                        name="edit_file",
                        arguments={
                            "path": "a.py",
                            "old_text": "A0",
                            "new_text": "A1",
                        },
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="tc2",
                        name="write_file",
                        arguments={"path": "b.py", "content": "B\n"},
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="ok", tool_calls=(), finish_reason="stop"),
        ]
    )
    agent = AgentService(store, llm=llm, max_steps=10)
    result = agent.run(session.session_id, "两步修改")
    assert (ws / "a.py").read_text(encoding="utf-8") == "A1\n"
    assert (ws / "b.py").read_text(encoding="utf-8") == "B\n"

    report = agent.revert_run(result.run.agent_run_id)
    assert report.ok
    assert (ws / "a.py").read_text(encoding="utf-8") == "A0\n"
    assert not (ws / "b.py").exists()
    # Run 历史仍在
    assert len(agent.list_run_file_changes(result.run.agent_run_id)) == 2


def test_revert_step_without_writes_raises(tmp_path: Path) -> None:
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "a.py").write_text("x\n", encoding="utf-8")
    store = SqliteStore(tmp_path / "cw.db")
    store.connect()
    session = SessionService(store).create_session(title="ro", workspace=ws)
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="tc_r",
                        name="read_file",
                        arguments={"path": "a.py"},
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="ok", tool_calls=(), finish_reason="stop"),
        ]
    )
    agent = AgentService(store, llm=llm, max_steps=5)
    result = agent.run(session.session_id, "只读")
    step_id = result.steps[0].step_id
    try:
        agent.revert_step(step_id)
        raised = False
    except RevertError:
        raised = True
    assert raised
