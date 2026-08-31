"""Dynamic Plan CLI：事件、渲染、隔离、重启。"""

from __future__ import annotations

from pathlib import Path

from backend.app.agent.event_sink import RecordingEventSink
from backend.app.agent.events import AgentEvent
from backend.app.cli.live_renderer import CliLiveRenderer
from backend.app.cli.render_plan import format_plan_panel, plan_from_domain
from backend.app.context.budget import ContextBudget
from backend.app.context.manager import DefaultContextManager
from backend.app.context.models import Plan, PlanStepStatus
from backend.app.context.plan_events import (
    PLAN_COMPLETED,
    PLAN_CREATED,
    PLAN_STEP_COMPLETED,
    PLAN_STEP_FAILED,
    PLAN_STEP_STARTED,
)
from backend.app.persistence.context_repository import ContextRepository
from backend.app.persistence.store import SqliteStore
from backend.app.session.service import SessionService


def test_plan_event_order_on_create_and_advance(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "t.db")
    store.connect()
    session = SessionService(store).create_session(
        workspace=str(tmp_path), title="A"
    )
    repo = ContextRepository(store)
    recorded = RecordingEventSink()
    cm = DefaultContextManager(
        session_id=session.session_id,
        workspace_root=str(tmp_path),
        budget=ContextBudget.from_context_window(32_000),
        repository=repo,
        event_emitter=recorded.emit,
    )
    cm.begin_run("修复 bug 并运行测试", agent_run_id=None)
    types = [e.event_type for e in recorded.events]
    assert PLAN_CREATED in types
    assert PLAN_STEP_STARTED in types
    assert types.index(PLAN_CREATED) < types.index(PLAN_STEP_STARTED)

    plan = cm.plan
    assert plan is not None
    step0 = sorted(plan.steps, key=lambda s: s.step_index)[0]
    cm._set_step_status(step0, PlanStepStatus.COMPLETED)  # noqa: SLF001
    cm._activate_next_plan_step()  # noqa: SLF001
    types2 = [e.event_type for e in recorded.events]
    assert PLAN_STEP_COMPLETED in types2
    assert types2.count(PLAN_STEP_STARTED) >= 2


def test_cli_renderer_step_transitions() -> None:
    outputs: list[str] = []
    r = CliLiveRenderer(output_fn=outputs.append, interactive=False)
    r.handle_plan_event(
        AgentEvent(
            event_type=PLAN_CREATED,
            step=0,
            metadata={
                "plan_id": "plan_1",
                "session_id": "ses",
                "goal": "g",
                "status": "in_progress",
                "steps": [
                    {
                        "step_id": "s0",
                        "step_index": 0,
                        "title": "Inspect",
                        "status": "in_progress",
                    },
                    {
                        "step_id": "s1",
                        "step_index": 1,
                        "title": "Fix",
                        "status": "pending",
                    },
                ],
            },
        )
    )
    r.handle_plan_event(
        AgentEvent(
            event_type=PLAN_STEP_COMPLETED,
            step=0,
            metadata={
                "plan_id": "plan_1",
                "step_id": "s0",
                "step_index": 0,
                "title": "Inspect",
                "status": "completed",
            },
        )
    )
    r.handle_plan_event(
        AgentEvent(
            event_type=PLAN_STEP_STARTED,
            step=0,
            metadata={
                "plan_id": "plan_1",
                "step_id": "s1",
                "step_index": 1,
                "title": "Fix",
                "status": "in_progress",
            },
        )
    )
    blob = "\n".join(outputs)
    assert "✓ 1. Inspect" in blob
    assert "● 2. Fix" in blob
    last = [o for o in outputs if isinstance(o, str) and o.startswith("Plan")][-1]
    assert "Inspect" in last
    assert "Fix" in last


def test_plan_step_failed_not_completed() -> None:
    outputs: list[str] = []
    r = CliLiveRenderer(output_fn=outputs.append, interactive=False)
    r.handle_plan_event(
        AgentEvent(
            event_type=PLAN_CREATED,
            step=0,
            metadata={
                "plan_id": "p",
                "steps": [
                    {
                        "step_id": "s0",
                        "step_index": 0,
                        "title": "Apply fix",
                        "status": "in_progress",
                    }
                ],
            },
        )
    )
    r.handle_plan_event(
        AgentEvent(
            event_type=PLAN_STEP_FAILED,
            step=0,
            metadata={
                "step_id": "s0",
                "step_index": 0,
                "title": "Apply fix",
                "status": "failed",
                "reason": "edit_file failed",
            },
        )
    )
    blob = "\n".join(outputs)
    assert "✗ 1. Apply fix" in blob
    assert "✓ 1. Apply fix" not in blob
    assert "edit_file failed" in blob


def test_plan_completed_banner() -> None:
    outputs: list[str] = []
    r = CliLiveRenderer(output_fn=outputs.append, interactive=False)
    r.handle_plan_event(
        AgentEvent(
            event_type=PLAN_CREATED,
            step=0,
            metadata={
                "plan_id": "p",
                "steps": [
                    {
                        "step_id": "s0",
                        "step_index": 0,
                        "title": "A",
                        "status": "pending",
                    }
                ],
            },
        )
    )
    r.handle_plan_event(
        AgentEvent(
            event_type=PLAN_COMPLETED,
            step=0,
            metadata={
                "plan_id": "p",
                "status": "completed",
                "steps": [
                    {
                        "step_id": "s0",
                        "step_index": 0,
                        "title": "A",
                        "status": "completed",
                    }
                ],
            },
        )
    )
    assert any("Plan completed" in line for line in outputs)


def test_session_plan_isolation(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "iso.db")
    store.connect()
    svc = SessionService(store)
    a = svc.create_session(workspace=str(tmp_path), title="A")
    b = svc.create_session(workspace=str(tmp_path), title="B")
    repo = ContextRepository(store)
    cm_a = DefaultContextManager(
        session_id=a.session_id,
        workspace_root=str(tmp_path),
        budget=ContextBudget.from_context_window(8_000),
        repository=repo,
    )
    cm_b = DefaultContextManager(
        session_id=b.session_id,
        workspace_root=str(tmp_path),
        budget=ContextBudget.from_context_window(8_000),
        repository=repo,
    )
    cm_a.begin_run("task A long enough goal text", agent_run_id=None)
    cm_b.begin_run("task B long enough goal text", agent_run_id=None)
    assert cm_a.plan is not None and cm_b.plan is not None
    assert cm_a.plan.plan_id != cm_b.plan.plan_id
    assert cm_a.plan.session_id == a.session_id
    assert cm_b.plan.session_id == b.session_id


def test_plan_persists_across_reload(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "reload.db")
    store.connect()
    session = SessionService(store).create_session(
        workspace=str(tmp_path), title="R"
    )
    repo = ContextRepository(store)
    cm = DefaultContextManager(
        session_id=session.session_id,
        workspace_root=str(tmp_path),
        budget=ContextBudget.from_context_window(8_000),
        repository=repo,
    )
    cm.begin_run("persist this plan goal text here", agent_run_id=None)
    assert cm.plan is not None
    pid = cm.plan.plan_id
    step = sorted(cm.plan.steps, key=lambda s: s.step_index)[0]
    cm._set_step_status(step, PlanStepStatus.COMPLETED)  # noqa: SLF001
    cm._save_plan()  # noqa: SLF001

    cm2 = DefaultContextManager(
        session_id=session.session_id,
        workspace_root=str(tmp_path),
        budget=ContextBudget.from_context_window(8_000),
        repository=repo,
    )
    cm2.load()
    assert cm2.plan is not None
    assert cm2.plan.plan_id == pid
    s0 = sorted(cm2.plan.steps, key=lambda s: s.step_index)[0]
    assert s0.status == PlanStepStatus.COMPLETED


def test_format_plan_panel_glyphs() -> None:
    plan = Plan.create(
        session_id="s",
        goal="g",
        step_titles=["Explore", "Implement", "Test"],
    )
    plan.steps[0].status = PlanStepStatus.COMPLETED
    plan.steps[1].status = PlanStepStatus.IN_PROGRESS
    text = format_plan_panel(plan_from_domain(plan))
    assert "✓ 1. Explore" in text
    assert "● 2. Implement" in text
    assert "○ 3. Test" in text
    assert "currently working" not in text


def test_agent_service_emits_plan_events(tmp_path: Path) -> None:
    """AgentService.run 经 ContextManager 发出 plan_*（非 CLI 伪造）。"""
    from backend.app.llm.client import LLMClient, LLMConfig
    from backend.app.llm.response import LLMResponse
    from backend.app.permissions.handler import AlwaysAllowPermissionHandler
    from backend.app.services.agent_service import AgentService

    class Scripted(LLMClient):
        def __init__(self) -> None:
            self.config = LLMConfig(api_key="x", base_url="http://x", model="fake")
            self._client = None  # type: ignore[assignment]
            self._queue = [LLMResponse(content="done", tool_calls=())]

        def chat(self, conversation, *, tools=None):  # noqa: ANN001
            return self._queue.pop(0)

    store = SqliteStore(tmp_path / "svc.db")
    store.connect()
    agents = AgentService(
        store,
        llm=Scripted(),
        permission_handler=AlwaysAllowPermissionHandler(),
    )
    session = agents.sessions.create_session(workspace=str(tmp_path), title="p")
    sink = RecordingEventSink()
    agents.run(session.session_id, "请探索并修复一个问题然后验证", event_sink=sink)
    types = [e.event_type for e in sink.events]
    assert PLAN_CREATED in types
    assert PLAN_STEP_STARTED in types
    assert types.index(PLAN_CREATED) < types.index("agent_completed")


def test_non_tty_plan_output_has_no_ansi() -> None:
    outputs: list[str] = []
    r = CliLiveRenderer(output_fn=outputs.append, interactive=False)
    r.handle_plan_event(
        AgentEvent(
            event_type=PLAN_CREATED,
            step=0,
            metadata={
                "plan_id": "p",
                "steps": [
                    {
                        "step_id": "s0",
                        "step_index": 0,
                        "title": "A",
                        "status": "in_progress",
                    }
                ],
            },
        )
    )
    blob = "\n".join(outputs)
    assert "\x1b[" not in blob
    assert "Plan #" in blob or "Plan" in blob


def test_compact_tool_activity_line() -> None:
    from backend.app.cli.live_renderer import compact_tool_activity

    line = compact_tool_activity(
        AgentEvent(
            event_type="tool_called",
            step=1,
            tool_name="read_file",
            metadata={"arguments": {"path": "src/taskflow/calculator.py"}},
        )
    )
    assert line.startswith("◇ read_file")
    assert "calculator.py" in line


def test_plan_advances_on_explore_then_edit(tmp_path: Path) -> None:
    from backend.app.tools.result import ToolResult

    store = SqliteStore(tmp_path / "adv.db")
    store.connect()
    session = SessionService(store).create_session(
        workspace=str(tmp_path), title="adv"
    )
    repo = ContextRepository(store)
    recorded = RecordingEventSink()
    cm = DefaultContextManager(
        session_id=session.session_id,
        workspace_root=str(tmp_path),
        budget=ContextBudget.from_context_window(32_000),
        repository=repo,
        event_emitter=recorded.emit,
    )
    cm.begin_run("阅读代码并修复问题然后验证", agent_run_id=None)
    assert cm.plan is not None
    titles = [s.title for s in sorted(cm.plan.steps, key=lambda s: s.step_index)]
    assert titles
    # 探索
    cm.update_after_tool(
        tool_name="read_file",
        tool_call_id="c1",
        arguments={"path": "src/a.py"},
        result=ToolResult(success=True, output={"line_count": 10}),
        observation="ok",
    )
    types = [e.event_type for e in recorded.events]
    assert PLAN_STEP_COMPLETED in types
    in_prog = [s for s in cm.plan.steps if s.status == PlanStepStatus.IN_PROGRESS]
    assert len(in_prog) == 1
    # 修改
    cm.update_after_tool(
        tool_name="edit_file",
        tool_call_id="c2",
        arguments={"path": "src/a.py"},
        result=ToolResult(success=True, output={"replacements": 1}),
        observation="edited",
    )
    completed = [s for s in cm.plan.steps if s.status == PlanStepStatus.COMPLETED]
    assert len(completed) >= 2
    cm.update_after_assistant("任务完成，测试通过。")
    assert cm.plan.status.value == "completed"
    assert any(e.event_type == PLAN_COMPLETED for e in recorded.events)


def test_plan_advances_design_step_on_read(tmp_path: Path) -> None:
    from backend.app.tools.result import ToolResult

    store = SqliteStore(tmp_path / "des.db")
    store.connect()
    session = SessionService(store).create_session(
        workspace=str(tmp_path), title="des"
    )
    repo = ContextRepository(store)
    cm = DefaultContextManager(
        session_id=session.session_id,
        workspace_root=str(tmp_path),
        budget=ContextBudget.from_context_window(32_000),
        repository=repo,
    )
    cm.begin_run("设计预算统计方案并实现", agent_run_id=None)
    assert cm.plan is not None
    # 强制当前步为「设计…」
    for s in cm.plan.steps:
        s.status = PlanStepStatus.PENDING
    cm.plan.steps[0].title = "设计预算统计字段扩展方案"
    cm.plan.steps[0].status = PlanStepStatus.IN_PROGRESS
    cm.update_after_tool(
        tool_name="read_file",
        tool_call_id="c1",
        arguments={"path": "a.py"},
        result=ToolResult(success=True, output={"line_count": 1}),
        observation="ok",
    )
    assert cm.plan.steps[0].status == PlanStepStatus.COMPLETED


def test_renderer_keeps_all_steps_when_created_again_with_one_step() -> None:
    """replan 只带回 1 步时，CLI 仍展示完整清单（Cursor 风格）。"""
    outputs: list[str] = []
    r = CliLiveRenderer(output_fn=outputs.append, interactive=False)
    steps = [
        {
            "step_id": f"s{i}",
            "step_index": i,
            "title": title,
            "status": "in_progress" if i == 0 else "pending",
        }
        for i, title in enumerate(
            ["定义需求", "实现匹配", "集成接口", "排序优化", "错误处理", "测试"]
        )
    ]
    r.handle_plan_event(
        AgentEvent(
            event_type=PLAN_CREATED,
            step=0,
            metadata={"plan_id": "plan_1", "steps": steps},
        )
    )
    r.handle_plan_event(
        AgentEvent(
            event_type=PLAN_CREATED,
            step=0,
            metadata={
                "plan_id": "plan_1",
                "steps": [
                    {
                        "step_id": "replan_only",
                        "step_index": 0,
                        "title": "定义需求",
                        "status": "failed",
                    }
                ],
            },
        )
    )
    last = [o for o in outputs if isinstance(o, str) and o.startswith("Plan")][-1]
    assert "1. 定义需求" in last
    assert "2. 实现匹配" in last
    assert "3. 集成接口" in last
    assert "4. 排序优化" in last
    assert "5. 错误处理" in last
    assert "6. 测试" in last
    view = r.plan_view
    assert view is not None
    assert len(view.steps) == 6


def test_format_plan_stable_height() -> None:
    from backend.app.cli.render_plan import format_plan_panel, plan_from_domain
    from backend.app.context.models import Plan, PlanStepStatus

    plan = Plan.create(
        session_id="s", goal="g", step_titles=["A", "B", "C"]
    )
    plan.steps[0].status = PlanStepStatus.IN_PROGRESS
    view = plan_from_domain(plan)
    view.activity = ""
    a = format_plan_panel(view, stable_height=True).split("\n")
    view.activity = "◇ read_file x.py"
    b = format_plan_panel(view, stable_height=True).split("\n")
    assert len(a) == len(b)
    plan.steps[0].status = PlanStepStatus.COMPLETED
    plan.steps[1].status = PlanStepStatus.IN_PROGRESS
    view = plan_from_domain(plan)
    c = format_plan_panel(view, stable_height=True).split("\n")
    assert len(c) == len(a)


def test_tool_activity_survives_step_transition() -> None:
    """步骤推进后仍保留工具活动行，不能被清成「…」。"""
    outputs: list[str] = []
    r = CliLiveRenderer(output_fn=outputs.append, interactive=False)
    r.handle_plan_event(
        AgentEvent(
            event_type=PLAN_CREATED,
            step=0,
            metadata={
                "plan_id": "p1",
                "steps": [
                    {
                        "step_id": "s0",
                        "step_index": 0,
                        "title": "Inspect",
                        "status": "in_progress",
                    },
                    {
                        "step_id": "s1",
                        "step_index": 1,
                        "title": "Fix",
                        "status": "pending",
                    },
                ],
            },
        )
    )
    r.handle_tool_event(
        AgentEvent(
            event_type="tool_completed",
            step=1,
            tool_name="read_file",
            metadata={"arguments": {"path": "a.py"}},
        )
    )
    r.handle_plan_event(
        AgentEvent(
            event_type=PLAN_STEP_COMPLETED,
            step=1,
            metadata={
                "step_id": "s0",
                "step_index": 0,
                "title": "Inspect",
                "status": "completed",
            },
        )
    )
    r.handle_plan_event(
        AgentEvent(
            event_type=PLAN_STEP_STARTED,
            step=1,
            metadata={
                "step_id": "s1",
                "step_index": 1,
                "title": "Fix",
                "status": "in_progress",
            },
        )
    )
    blob = "\n".join(outputs)
    assert "read_file" in blob
    assert "a.py" in blob
    last = [o for o in outputs if isinstance(o, str) and o.startswith("Plan")][-1]
    assert "…" not in last or "read_file" in last
    assert "read_file" in last


def test_speculative_answer_delta_does_not_stop_plan_or_print() -> None:
    """工具轮推测正文不写屏、不冻 Plan；discard 后工具行仍可更新。"""
    from backend.app.cli.event_sink import CliEventSink

    streamed: list[str] = []
    plan_out: list[str] = []
    sink = CliEventSink(
        output_fn=plan_out.append,
        stream_write_fn=streamed.append,
        model_id="fake",
        enable_markdown=False,
    )
    sink._interactive = False  # noqa: SLF001
    sink._capture_answer = False  # noqa: SLF001
    sink._renderer._interactive = False  # noqa: SLF001
    sink._renderer._output_fn = plan_out.append  # noqa: SLF001

    sink.emit(
        AgentEvent(
            event_type=PLAN_CREATED,
            step=0,
            metadata={
                "plan_id": "p1",
                "steps": [
                    {
                        "step_id": "s0",
                        "step_index": 0,
                        "title": "A",
                        "status": "in_progress",
                    }
                ],
            },
        )
    )
    sink.emit(
        AgentEvent(
            event_type="answer_delta",
            step=1,
            metadata={"delta": "让我先思考一下"},
        )
    )
    assert streamed == []
    assert sink._renderer._stopped is False  # noqa: SLF001
    sink.emit(AgentEvent(event_type="answer_discard", step=1, metadata={}))
    assert sink._answer_buf == ""  # noqa: SLF001

    sink.emit(
        AgentEvent(
            event_type="tool_completed",
            step=1,
            tool_name="read_file",
            metadata={"arguments": {"path": "x.py"}},
        )
    )
    blob = "\n".join(plan_out)
    assert "read_file" in blob
    assert "x.py" in blob
    assert "让我先思考" not in blob
    assert "让我先思考" not in "".join(streamed)


def test_final_answer_streams_live_after_plan_finished() -> None:
    """Plan 全部 ✓ 后，answer_delta 真流式写屏（不再空等整段再 MD）。"""
    from backend.app.cli.event_sink import CliEventSink

    streamed: list[str] = []
    sink = CliEventSink(
        output_fn=print,
        stream_write_fn=streamed.append,
        model_id="fake",
        enable_markdown=False,
    )
    sink._interactive = False  # noqa: SLF001
    sink._capture_answer = False  # noqa: SLF001
    sink._renderer._interactive = False  # noqa: SLF001

    sink.emit(
        AgentEvent(
            event_type=PLAN_CREATED,
            step=0,
            metadata={
                "plan_id": "p1",
                "steps": [
                    {
                        "step_id": "s0",
                        "step_index": 0,
                        "title": "A",
                        "status": "completed",
                    },
                    {
                        "step_id": "s1",
                        "step_index": 1,
                        "title": "B",
                        "status": "completed",
                    },
                ],
            },
        )
    )
    sink.emit(
        AgentEvent(
            event_type=PLAN_COMPLETED,
            step=0,
            metadata={
                "plan_id": "p1",
                "status": "completed",
                "steps": [
                    {
                        "step_id": "s0",
                        "step_index": 0,
                        "title": "A",
                        "status": "completed",
                    },
                    {
                        "step_id": "s1",
                        "step_index": 1,
                        "title": "B",
                        "status": "completed",
                    },
                ],
            },
        )
    )
    sink.emit(AgentEvent(event_type="answer_delta", step=2, metadata={"delta": "你"}))
    sink.emit(AgentEvent(event_type="answer_delta", step=2, metadata={"delta": "好"}))
    assert "你好" in "".join(streamed)


def test_clear_streamed_draft_never_uses_erase_display() -> None:
    """清草稿不得用 CSI J，否则会误删上方 Plan。"""
    from pathlib import Path

    from backend.app.cli.event_sink import _visual_rows

    src = Path("backend/app/cli/event_sink.py").read_text(encoding="utf-8")
    assert "\\033[J" not in src
    assert "\\033[0J" not in src
    # CJK 按双宽计行，避免低估/高估
    assert _visual_rows("你好世界", 4) == 2
    assert _visual_rows("abcd", 4) == 1


def test_renderer_source_does_not_use_live_or_erase_display() -> None:
    """不用 Rich Live；不用 CSI J 清整屏。"""
    from pathlib import Path

    src = Path("backend/app/cli/live_renderer.py").read_text(encoding="utf-8")
    assert "rich.live" not in src
    assert "Live(" not in src
    assert "\\033[J" not in src
    assert "stable_height" in Path("backend/app/cli/render_plan.py").read_text(
        encoding="utf-8"
    )
