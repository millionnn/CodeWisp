"""V0.9 Phase 2：AgentStep Change Tracking 集成与重启恢复。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.app.agent.state import AgentStatus
from backend.app.changes.models import ChangeType
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.persistence.store import SqliteStore
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


def test_edit_file_tracks_step_and_run_changes(tmp_path: Path) -> None:
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "calc.py").write_text("return a - b\n", encoding="utf-8")
    db_path = tmp_path / "cw.db"
    store = SqliteStore(db_path)
    store.connect()

    sessions = SessionService(store)
    session = sessions.create_session(title="chg", workspace=ws)
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
            LLMResponse(content="已修好加法。", tool_calls=(), finish_reason="stop"),
        ]
    )
    agent = AgentService(store, llm=llm, max_steps=5)
    result = agent.run(session.session_id, "修 bug")
    assert result.state.status == AgentStatus.COMPLETED
    assert (ws / "calc.py").read_text(encoding="utf-8") == "return a + b\n"

    changes = agent.list_run_file_changes(result.run.agent_run_id)
    assert len(changes) == 1
    assert changes[0].path == "calc.py"
    assert changes[0].change_type is ChangeType.MODIFIED
    assert changes[0].tool_call_id == "tc_edit1"
    assert changes[0].agent_step_id.startswith("step_")

    step_id = changes[0].agent_step_id
    step_changes = agent.list_step_file_changes(step_id)
    assert len(step_changes) == 1

    before, after = agent.get_step_snapshots(step_id)
    assert before is not None and after is not None
    assert before.reason == "pre_step"
    assert after.reason == "post_step"
    assert before.file_map()["calc.py"].content == "return a - b\n"
    assert after.file_map()["calc.py"].content == "return a + b\n"

    before_tool = agent.get_snapshot(changes[0].before_snapshot_id or "")
    after_tool = agent.get_snapshot(changes[0].after_snapshot_id or "")
    assert before_tool.tool_call_id == "tc_edit1"
    assert after_tool.files[0].content == "return a + b\n"

    # 重启后仍可查询
    store.close()
    store2 = SqliteStore(db_path)
    store2.connect()
    agent2 = AgentService(
        store2,
        llm=ScriptedLLMClient([]),
        max_steps=5,
    )
    resumed = agent2.list_run_file_changes(result.run.agent_run_id)
    assert len(resumed) == 1
    assert resumed[0].change_type is ChangeType.MODIFIED
    b2, a2 = agent2.get_step_snapshots(step_id)
    assert b2 is not None and a2 is not None
    assert a2.file_map()["calc.py"].content == "return a + b\n"


def test_write_file_tracks_added(tmp_path: Path) -> None:
    ws = tmp_path / "proj"
    ws.mkdir()
    store = SqliteStore(tmp_path / "cw.db")
    store.connect()
    session = SessionService(store).create_session(title="w", workspace=ws)
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="tc_write1",
                        name="write_file",
                        arguments={"path": "hello.txt", "content": "hi\n"},
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="写好了。", tool_calls=(), finish_reason="stop"),
        ]
    )
    agent = AgentService(store, llm=llm, max_steps=5)
    result = agent.run(session.session_id, "新建文件")
    changes = agent.list_run_file_changes(result.run.agent_run_id)
    assert len(changes) == 1
    assert changes[0].change_type is ChangeType.ADDED
    assert changes[0].path == "hello.txt"
    assert (ws / "hello.txt").read_text(encoding="utf-8") == "hi\n"


def test_read_only_tools_do_not_create_file_changes(tmp_path: Path) -> None:
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "a.py").write_text("x=1\n", encoding="utf-8")
    store = SqliteStore(tmp_path / "cw.db")
    store.connect()
    session = SessionService(store).create_session(title="r", workspace=ws)
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="tc_read",
                        name="read_file",
                        arguments={"path": "a.py"},
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="读完了。", tool_calls=(), finish_reason="stop"),
        ]
    )
    agent = AgentService(store, llm=llm, max_steps=5)
    result = agent.run(session.session_id, "读文件")
    assert agent.list_run_file_changes(result.run.agent_run_id) == []
