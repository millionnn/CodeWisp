"""V0.6 Phase 2-F：端到端集成 + 架构边界回归。

覆盖 Phase 2 验收：
Session CRUD / Conversation / AgentRun·Step·ToolCall /
Restart / Isolation / Provider·Model snapshot / Undo ID readiness /
AgentLoop 不依赖 SQLite。
"""

from __future__ import annotations

import ast
from pathlib import Path
from typing import Any

import pytest

from backend.app.agent.state import AgentStatus
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.persistence.errors import NotFoundError
from backend.app.persistence.agent_run_repository import AgentRunRepository
from backend.app.persistence.store import SqliteStore
from backend.app.services.agent_service import AgentService
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


def _responses_tool_then_text() -> list[LLMResponse]:
    return [
        LLMResponse(
            content=None,
            tool_calls=(
                ToolCall(
                    id="call_calc",
                    name="calculator",
                    arguments={"expression": "3*3"},
                    arguments_raw='{"expression":"3*3"}',
                ),
            ),
            finish_reason="tool_calls",
        ),
        LLMResponse(content="9", tool_calls=(), finish_reason="stop"),
    ]


def test_phase2_e2e_session_run_step_restart_continue(tmp_path: Path) -> None:
    """完整链路：创建 → 执行（含 tool）→ 关进程 → 恢复 → 续跑 → 校验 ID 图。"""
    ws = tmp_path / "workspace-a"
    ws.mkdir()
    db_path = tmp_path / "phase2.db"

    # Process 1
    store1 = SqliteStore(db_path)
    store1.connect()
    sessions1 = SessionService(store1)
    session = sessions1.create_session(
        title="Phase2 E2E",
        workspace=ws,
        provider_id="deepseek",
        model_id="deepseek-chat",
    )
    sid = session.session_id

    agent1 = AgentService(store1, llm=ScriptedLLMClient(_responses_tool_then_text()), max_steps=8)
    result1 = agent1.run(sid, "计算 3*3")
    assert result1.state.status == AgentStatus.COMPLETED
    assert result1.run.provider_id == "deepseek"
    assert result1.run.model_id == "deepseek-chat"
    assert result1.run.termination_reason == "completed"
    assert len(result1.steps) == 2
    run_id = result1.run.agent_run_id
    step_ids = {s.step_index: s.step_id for s in result1.steps}
    assert all(sid_.startswith("step_") for sid_ in step_ids.values())

    runs_repo = AgentRunRepository(store1)
    tools = runs_repo.list_tool_calls(agent_run_id=run_id)
    assert len(tools) == 1
    assert tools[0].tool_call_id == "call_calc"
    assert tools[0].step_id == step_ids[1]
    store1.close()

    # Process 2 — resume + continue
    store2 = SqliteStore(db_path)
    store2.connect()
    agent2 = AgentService(
        store2,
        llm=ScriptedLLMClient(
            [LLMResponse(content="上一轮结果是 9", tool_calls=(), finish_reason="stop")]
        ),
        max_steps=8,
    )
    resumed = agent2.resume(sid)
    assert resumed.session.title == "Phase2 E2E"
    assert resumed.workspace == str(ws.resolve())
    assert resumed.run_count == 1
    assert resumed.latest_run is not None
    assert resumed.latest_run.agent_run_id == run_id
    roles = [m.role for m in resumed.conversation.messages]
    assert roles[0] == "system"
    assert "tool" in roles
    assert sum(1 for r in roles if r == "system") == 1

    result2 = agent2.continue_session(sid, "结果是多少？")
    assert result2.state.status == AgentStatus.COMPLETED
    assert result2.run.agent_run_id != run_id

    # LLM 续跑看到历史 tool trajectory
    hist = agent2._llm.calls[0]["messages"]  # type: ignore[union-attr]
    assert any(m.get("role") == "tool" for m in hist)
    assert any(m.get("content") == "计算 3*3" for m in hist)

    final = agent2.resume(sid)
    assert final.run_count == 2
    assert [r.termination_reason for r in final.runs] == ["completed", "completed"]

    # Undo readiness：稳定 ID 仍可从 DB 读出
    runs2 = AgentRunRepository(store2)
    assert runs2.get_step(step_ids[1]).agent_run_id == run_id
    assert runs2.get_tool_call("call_calc").step_id == step_ids[1]
    store2.close()


def test_phase2_e2e_session_isolation_workspaces_and_history(tmp_path: Path) -> None:
    ws_a = tmp_path / "proj-a"
    ws_b = tmp_path / "proj-b"
    ws_a.mkdir()
    ws_b.mkdir()
    store = SqliteStore(tmp_path / "iso.db")
    store.connect()

    sessions = SessionService(store)
    sa = sessions.create_session(
        title="A", workspace=ws_a, provider_id="deepseek", model_id="deepseek-chat"
    )
    sb = sessions.create_session(
        title="B", workspace=ws_b, provider_id="openai", model_id="gpt-test"
    )

    agent = AgentService(
        store,
        llm=ScriptedLLMClient(
            [
                LLMResponse(content="answer-a", tool_calls=()),
                LLMResponse(content="answer-b", tool_calls=()),
            ]
        ),
    )
    ra = agent.run(sa.session_id, "task-a")
    rb = agent.run(sb.session_id, "task-b")

    assert ra.run.provider_id == "deepseek"
    assert rb.run.provider_id == "openai"
    assert ra.session.workspace != rb.session.workspace

    resume_a = sessions.resume_session(sa.session_id)
    resume_b = sessions.resume_session(sb.session_id)
    assert all(m.content != "task-b" for m in resume_a.conversation.messages if m.role == "user")
    assert all(m.content != "task-a" for m in resume_b.conversation.messages if m.role == "user")
    assert resume_a.latest_run is not None and resume_a.latest_run.model_id == "deepseek-chat"
    assert resume_b.latest_run is not None and resume_b.latest_run.model_id == "gpt-test"


def test_phase2_e2e_delete_session_cascades_all_artifacts(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    store = SqliteStore(tmp_path / "del.db")
    store.connect()
    sessions = SessionService(store)
    session = sessions.create_session(title="del", workspace=ws)
    agent = AgentService(store, llm=ScriptedLLMClient(_responses_tool_then_text()))
    result = agent.run(session.session_id, "go")
    run_id = result.run.agent_run_id

    sessions.delete_session(session.session_id)

    assert store.execute("SELECT COUNT(*) FROM sessions").fetchone()[0] == 0
    assert store.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
    assert store.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0] == 0
    assert store.execute("SELECT COUNT(*) FROM agent_steps").fetchone()[0] == 0
    assert store.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0] == 0

    runs = AgentRunRepository(store)
    with pytest.raises(NotFoundError):
        runs.get_run(run_id)


def test_phase2_crud_roundtrip_via_services(tmp_path: Path) -> None:
    ws = tmp_path / "ws"
    ws.mkdir()
    store = SqliteStore(tmp_path / "crud.db")
    store.connect()
    sessions = SessionService(store)

    created = sessions.create_session(title="t1", workspace=ws)
    listed = sessions.list_sessions()
    assert any(s.session_id == created.session_id for s in listed)
    renamed = sessions.rename_session(created.session_id, "t2")
    assert renamed.title == "t2"
    got = sessions.get_session(created.session_id)
    assert got.title == "t2"
    assert got.provider_id == "deepseek"
    sessions.delete_session(created.session_id)
    assert sessions.list_sessions() == []


def _module_imports(path: Path) -> set[str]:
    source = path.read_text(encoding="utf-8")
    tree = ast.parse(source, filename=str(path))
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                names.add(alias.name)
        elif isinstance(node, ast.ImportFrom) and node.module:
            names.add(node.module)
    return names


def test_phase2_architecture_agent_core_has_no_sqlite_or_persistence() -> None:
    repo = Path(__file__).resolve().parents[1]
    roots = [
        repo / "backend/app/agent",
        repo / "backend/app/tools",
        repo / "backend/app/workspace",
        repo / "backend/app/execution",
        repo / "backend/app/llm",
    ]
    violations: list[str] = []
    for root in roots:
        for path in root.rglob("*.py"):
            for mod in _module_imports(path):
                if mod == "sqlite3" or mod.startswith("sqlite3."):
                    violations.append(f"{path}: {mod}")
                if mod == "backend.app.persistence" or mod.startswith(
                    "backend.app.persistence."
                ):
                    violations.append(f"{path}: {mod}")
    assert violations == [], violations


def test_phase2_schema_version_includes_v4_semantic(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "schema.db")
    store.connect()
    assert store.schema_version() == 4
