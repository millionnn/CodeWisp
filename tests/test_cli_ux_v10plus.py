"""CLI UX：Plan 面板符号 / Footer / Session 标题。"""

from __future__ import annotations

from backend.app.cli.render_plan import format_plan_panel, plan_from_domain
from backend.app.cli.status_bar import (
    DEFAULT_SESSION_TITLES,
    StatusBarState,
    summarize_session_title,
)
from backend.app.cli.theme import reset_theme_cache
from backend.app.context.models import Plan, PlanStepStatus


def test_summarize_session_title() -> None:
    assert summarize_session_title("hello") == "hello"
    long = "a" * 80
    assert summarize_session_title(long).endswith("…")
    assert len(summarize_session_title(long)) == 48
    assert "CLI Session" in DEFAULT_SESSION_TITLES


def test_format_plan_claude_code_style() -> None:
    plan = Plan.create(
        session_id="ses_x",
        goal="Add feature",
        step_titles=["Explore", "Implement", "Test"],
    )
    plan.steps[0].status = PlanStepStatus.COMPLETED
    plan.steps[1].status = PlanStepStatus.IN_PROGRESS
    text = format_plan_panel(plan_from_domain(plan))
    assert "✓ 1. Explore" in text
    assert "● 2. Implement" in text
    assert "○ 3. Test" in text


def test_opencode_style_footer() -> None:
    bar = StatusBarState()
    bar.update_workspace("/Users/me/projects/codewisp-test-repo")
    bar.snapshot.session_id = "ses_abcdefghijklmnop"
    bar.snapshot.title = "my task title that is quite long for display"
    bar.snapshot.model = "deepseek/deepseek-chat"
    bar.update_context(used=19100, budget=58900)
    line = bar.snapshot.line(width=120)
    assert "codewisp-test-repo" in line
    assert "deepseek-chat" in line
    # 完整 token，不缩写成 k
    assert "ctx 19,100/58,900" in line
    assert "19.1k" not in line
    right = bar.snapshot.right()
    assert " · " in right
    assert bar.snapshot.context_label() == "ctx 19,100/58,900"
    # 未知用量时显示 0，不出现 —
    bar.update_context(used=None, budget=None)
    assert bar.snapshot.context_label() == "ctx 0"


def test_terminal_width_follows_window(monkeypatch) -> None:
    from backend.app.cli import theme as theme_mod

    reset_theme_cache()

    class _Size:
        columns = 140
        lines = 40

    monkeypatch.setattr(theme_mod.os, "get_terminal_size", lambda *a, **k: _Size())
    assert theme_mod.terminal_width() == 140
    _Size.columns = 90
    assert theme_mod.terminal_width() == 90


def test_quiet_tools_plan_shows_compact_activity() -> None:
    """默认 Plan 下挂一行工具摘要，不刷完整 Step 轨迹。"""
    from backend.app.agent.events import AgentEvent
    from backend.app.cli.event_sink import CliEventSink
    from backend.app.context.models import Plan, PlanStepStatus
    from backend.app.context.plan_events import PLAN_CREATED

    plan = Plan.create(session_id="s", goal="g", step_titles=["A", "B"])
    plan.steps[0].status = PlanStepStatus.IN_PROGRESS
    outputs: list[str] = []
    sink = CliEventSink(
        output_fn=outputs.append,
        model_id="fake",
        plan_provider=lambda: plan,
        show_tool_trace=False,
    )
    sink.emit(
        AgentEvent(
            event_type=PLAN_CREATED,
            step=0,
            metadata={
                "plan_id": plan.plan_id,
                "session_id": "s",
                "goal": "g",
                "status": "in_progress",
                "steps": [
                    {
                        "step_id": plan.steps[0].step_id,
                        "step_index": 0,
                        "title": "A",
                        "status": "in_progress",
                    },
                    {
                        "step_id": plan.steps[1].step_id,
                        "step_index": 1,
                        "title": "B",
                        "status": "pending",
                    },
                ],
            },
        )
    )
    sink.emit(
        AgentEvent(
            event_type="tool_called",
            step=1,
            tool_name="read_file",
            metadata={"arguments": {"path": "x.py"}},
        )
    )
    blob = "\n".join(outputs)
    assert "● 1. A" in blob
    assert "read_file" in blob
    assert "x.py" in blob
    assert "◇ read_file" in blob or "read_file" in blob
    # 默认不打印完整 Step/参数块
    assert "Step 1" not in blob
