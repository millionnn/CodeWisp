"""V1.0 Hierarchical Context Management 测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.app.agent.loop import AgentLoop
from backend.app.context.budget import ContextBudget
from backend.app.context.manager import DefaultContextManager
from backend.app.context.models import (
    CheckpointTrigger,
    MemoryCategory,
    MemoryItem,
    MemorySourceType,
    TaskState,
)
from backend.app.context.priority import ContextPriority
from backend.app.context.project_rules import discover_project_rules
from backend.app.context.tool_output import ToolOutputPolicy, prune_tool_observation
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.messages import Conversation, Message
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.persistence.context_repository import ContextRepository
from backend.app.persistence.store import SqliteStore
from backend.app.permissions.handler import AlwaysAllowPermissionHandler
from backend.app.services.agent_service import AgentService
from backend.app.session.service import SessionService
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry
from backend.app.tools.result import ToolResult
from backend.app.workspace.workspace import Workspace


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
            from backend.app.llm.errors import LLMRequestError

            raise LLMRequestError("无更多脚本响应")
        return self._queue.pop(0)


def _budget(window: int = 8_000) -> ContextBudget:
    return ContextBudget.from_context_window(
        window, reserved_output_tokens=500, safety_buffer=100
    )


# ── Budget ─────────────────────────────────────────────────────


def test_budget_below_near_over() -> None:
    b = _budget(1000)
    assert b.usable_budget == 1000 - 500 - 100
    assert b.fits(100)
    assert b.remaining(100) == b.usable_budget - 100
    assert not b.fits(b.usable_budget + 1)
    assert b.estimator == "heuristic_chars"


def test_budget_fallback_when_no_window() -> None:
    b = ContextBudget.from_context_window(None)
    assert b.context_limit == 32_000
    assert b.usable_budget > 0


# ── Tool output ────────────────────────────────────────────────


def test_tool_output_prunes_large_stdout() -> None:
    huge = "\n".join(f"line {i} " + ("x" * 40) for i in range(5000))
    pruned = prune_tool_observation(huge, tool_name="run_command")
    assert len(pruned) < len(huge)
    assert "truncated" in pruned.lower()


def test_tool_output_policy_lines_and_chars() -> None:
    pol = ToolOutputPolicy(max_chars=500, max_lines=20, head_lines=5, tail_lines=5)
    text = "\n".join(f"L{i}" for i in range(100))
    out = pol.truncate(text, label="search")
    assert "truncated" in out.lower()
    assert len(out.splitlines()) < 100


# ── Project rules ──────────────────────────────────────────────


def test_project_rules_root_and_nested(tmp_path: Path) -> None:
    (tmp_path / "AGENTS.md").write_text("# Root\nuse pytest", encoding="utf-8")
    backend = tmp_path / "backend"
    backend.mkdir()
    (backend / "AGENTS.md").write_text("# Backend\nno print", encoding="utf-8")
    (tmp_path / "frontend").mkdir()
    (tmp_path / "frontend" / "CLAUDE.md").write_text("# FE\nuse vite", encoding="utf-8")

    root_only = discover_project_rules(tmp_path, focus_path=None)
    assert len(root_only) == 1
    assert root_only[0].path == "AGENTS.md"

    nested = discover_project_rules(tmp_path, focus_path="backend/auth/service.py")
    paths = {r.path for r in nested}
    assert "AGENTS.md" in paths
    assert "backend/AGENTS.md" in paths

    # 相同内容不重复：再写一份相同 hash 的文件
    (tmp_path / "CLAUDE.md").write_text("# Root\nuse pytest", encoding="utf-8")
    # AGENTS.md 优先，CLAUDE.md 同内容会被 skip（不同 path 但同 hash）
    again = discover_project_rules(tmp_path)
    assert sum(1 for r in again if r.content_hash == again[0].content_hash) == 1


# ── Memory + provenance + session isolation ─────────────────────


def test_memory_create_provenance_and_session_isolation(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "ctx.db")
    store.connect()
    # 需要 sessions 行以满足 FK
    svc = SessionService(store)
    a = svc.create_session(workspace=str(tmp_path), title="A")
    b = svc.create_session(workspace=str(tmp_path), title="B")
    repo = ContextRepository(store)

    item = MemoryItem.create(
        session_id=a.session_id,
        category=MemoryCategory.ARCHITECTURE,
        content="token refresh bug is in AuthService",
        source_type=MemorySourceType.TOOL_OBSERVATION,
        source_id="tc_abc",
        file_path="backend/auth/service.py",
        line_start=72,
        line_end=91,
        priority=ContextPriority.P1,
    )
    repo.save_memory(item)
    listed = repo.list_memories(a.session_id)
    assert len(listed) == 1
    assert listed[0].source_id == "tc_abc"
    assert listed[0].file_path == "backend/auth/service.py"
    assert repo.list_memories(b.session_id) == []


# ── Compaction ─────────────────────────────────────────────────


def test_compaction_preserves_raw_history_and_creates_checkpoint(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "c.db")
    store.connect()
    svc = SessionService(store)
    session = svc.create_session(workspace=str(tmp_path), title="c")
    repo = ContextRepository(store)

    cm = DefaultContextManager(
        session_id=session.session_id,
        workspace_root=str(tmp_path),
        budget=_budget(2_000),
        repository=repo,
        recent_tail_messages=4,
    )
    cm.begin_run("fix auth module thoroughly with tests")

    conv = Conversation()
    conv.add_system("SYSTEM_RULES_MUST_STAY")
    for i in range(40):
        conv.add_user(f"user message {i} " + ("word " * 80))
        conv.add_assistant(f"assistant reply {i} " + ("text " * 80))
        conv.add_tool_result(f"call_{i}", "x" * 2000)

    raw_len = len(conv.messages)
    view = cm.build_context(conv, tools=[])
    assert any(m.role == "system" and "SYSTEM_RULES_MUST_STAY" in (m.content or "") for m in view.messages)
    # durable conversation 未删
    assert len(conv.messages) == raw_len
    # 视图更短或含 checkpoint
    status = cm.status()
    assert status.total_tokens <= cm.budget.usable_budget + 200  # 允许粗估误差余量
    assert cm.latest_checkpoint is not None

    manual = cm.compact(conv, trigger=CheckpointTrigger.MANUAL)
    assert manual.trigger == CheckpointTrigger.MANUAL
    assert repo.get_latest_checkpoint(session.session_id) is not None
    assert len(conv.messages) == raw_len


def test_priority_p0_never_removed(tmp_path: Path) -> None:
    cm = DefaultContextManager(
        session_id="ses_x",
        workspace_root=str(tmp_path),
        budget=_budget(1500),
        repository=None,
        persist=False,
        recent_tail_messages=3,
    )
    cm.begin_run("tiny budget task")
    conv = Conversation()
    conv.add_system("P0_SYSTEM_PROMPT")
    for i in range(30):
        conv.add_user("u" * 400)
        conv.add_assistant("a" * 400)
    view = cm.build_context(conv)
    systems = [m.content or "" for m in view.messages if m.role == "system"]
    assert any("P0_SYSTEM_PROMPT" in s for s in systems)


# ── AgentLoop integration ──────────────────────────────────────


def test_agent_loop_uses_context_manager_view(tmp_path: Path) -> None:
    cm = DefaultContextManager(
        session_id="ses_loop",
        workspace_root=str(tmp_path),
        budget=_budget(64_000),
        persist=False,
    )
    cm.begin_run("say hi")
    llm = ScriptedLLMClient([LLMResponse(content="hello", tool_calls=())])
    reg = create_default_registry()
    loop = AgentLoop(llm, ToolExecutor(reg), reg, context_manager=cm)
    state = loop.run("hello")
    assert state.final_answer == "hello"
    # LLM 看到分层上下文（Task / Plan）
    joined = str(llm.calls[0]["messages"])
    assert "Task State" in joined or "Plan" in joined


def test_agent_loop_prunes_tool_observation(tmp_path: Path) -> None:
    cm = DefaultContextManager(
        session_id="ses_prune",
        workspace_root=str(tmp_path),
        budget=_budget(64_000),
        persist=False,
        tool_output_policy=ToolOutputPolicy(max_chars=300, max_lines=10),
    )
    cm.begin_run("run something")

    huge = "\n".join(f"out {i}" for i in range(2000))
    # calculator 不够大；用自定义结果通过 update_after_tool 测 prune_observation
    pruned = cm.prune_observation(huge, tool_name="run_command")
    assert len(pruned) < len(huge)

    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="calculator",
                        arguments={"expression": "1+1"},
                        arguments_raw='{"expression":"1+1"}',
                    ),
                ),
            ),
            LLMResponse(content="done", tool_calls=()),
        ]
    )
    reg = create_default_registry()
    loop = AgentLoop(llm, ToolExecutor(reg), reg, context_manager=cm, max_steps=5)
    state = loop.run("calc")
    assert state.final_answer == "done"


# ── Revert invalidation ────────────────────────────────────────


def test_revert_invalidates_workspace_context(tmp_path: Path) -> None:
    ws_root = tmp_path / "proj"
    ws_root.mkdir()
    (ws_root / "a.py").write_text("v1\n", encoding="utf-8")

    store = SqliteStore(tmp_path / "r.db")
    store.connect()
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="w1",
                        name="edit_file",
                        arguments={
                            "path": "a.py",
                            "old_text": "v1",
                            "new_text": "v2",
                        },
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="wrote", tool_calls=(), finish_reason="stop"),
        ]
    )
    agents = AgentService(
        store,
        llm=llm,
        permission_handler=AlwaysAllowPermissionHandler(),
        max_steps=5,
    )
    session = agents.sessions.create_session(workspace=ws_root, title="rev")
    result = agents.run(session.session_id, "please edit a.py")
    assert (ws_root / "a.py").read_text(encoding="utf-8") == "v2\n"

    cm = agents.get_context_manager(session.session_id)
    mem = MemoryItem.create(
        session_id=session.session_id,
        category=MemoryCategory.IMPORTANT_FACT,
        content="a.py now contains v2",
        source_type=MemorySourceType.AGENT,
        file_path="a.py",
    )
    cm._add_memory(mem)  # noqa: SLF001

    assert result.steps
    report = agents.revert_step(
        result.steps[0].step_id,
        permission_handler=AlwaysAllowPermissionHandler(),
    )
    assert report.ok
    assert (ws_root / "a.py").read_text(encoding="utf-8") == "v1\n"

    cm2 = agents.get_context_manager(session.session_id)
    assert cm2.task is not None
    assert cm2.task.workspace_state.stale is True
    memories = agents.list_memories(session.session_id, include_invalidated=True)
    assert any(m.invalidated and m.file_path == "a.py" for m in memories)
    view = cm2.build_context(Conversation())
    text = "\n".join(m.content or "" for m in view.messages if m.role == "system")
    assert "STALE" in text or "stale" in text.lower() or "revert" in text.lower()


# ── Restart recovery ───────────────────────────────────────────


def test_context_survives_process_restart(tmp_path: Path) -> None:
    db = tmp_path / "restart.db"
    store = SqliteStore(db)
    store.connect()
    svc = SessionService(store)
    session = svc.create_session(workspace=str(tmp_path), title="restart")
    repo = ContextRepository(store)
    cm = DefaultContextManager(
        session_id=session.session_id,
        workspace_root=str(tmp_path),
        budget=_budget(),
        repository=repo,
    )
    cm.begin_run("long coding task about auth")
    assert cm.task is not None
    assert cm.plan is not None
    task_id = cm.task.task_id
    plan_id = cm.plan.plan_id
    store.close()

    store2 = SqliteStore(db)
    store2.connect()
    repo2 = ContextRepository(store2)
    cm2 = DefaultContextManager(
        session_id=session.session_id,
        workspace_root=str(tmp_path),
        budget=_budget(),
        repository=repo2,
    )
    cm2.load()
    assert cm2.task is not None
    assert cm2.task.task_id == task_id
    assert cm2.plan is not None
    assert cm2.plan.plan_id == plan_id


# ── Session isolation via AgentService ─────────────────────────


def test_session_context_isolation(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "iso.db")
    store.connect()
    llm = ScriptedLLMClient(
        [LLMResponse(content="ok A", tool_calls=()), LLMResponse(content="ok B", tool_calls=())]
    )
    agents = AgentService(store, llm=llm, max_steps=3)
    sa = agents.sessions.create_session(workspace=str(tmp_path), title="A")
    sb = agents.sessions.create_session(workspace=str(tmp_path), title="B")
    agents.run(sa.session_id, "task for session A only")
    agents.run(sb.session_id, "task for session B only")
    ta = agents.get_active_task(sa.session_id)
    tb = agents.get_active_task(sb.session_id)
    assert ta is not None and tb is not None
    assert ta.task_id != tb.task_id
    assert "A" in ta.goal or "session A" in ta.goal
    assert "B" in tb.goal or "session B" in tb.goal
