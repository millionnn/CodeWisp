"""Plan 面板文本格式（CLI 渲染；无状态推理）。

符号（NO_COLOR / 非 TTY 同样可读）：
  ✓ completed · ● in_progress · ○ pending · ✗ failed · ⊘ skipped
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from backend.app.cli.theme import get_theme, make_console, terminal_width
from backend.app.context.models import Plan, PlanStepStatus

STATUS_GLYPH: dict[str, str] = {
    "completed": "✓",
    "in_progress": "●",
    "pending": "○",
    "failed": "✗",
    "blocked": "✗",
    "skipped": "⊘",
    "cancelled": "⊘",
}


@dataclass
class PlanStepView:
    step_id: str
    step_index: int
    title: str
    status: str
    reason: str | None = None
    # 本步骤下只挂一行工具摘要（刷新，不堆多行）
    tool_line: str = ""


@dataclass
class PlanView:
    """CLI 展示用的 Plan 视图（仅由 plan_* 事件驱动更新）。"""

    plan_id: str = ""
    session_id: str = ""
    goal: str = ""
    status: str = "pending"
    steps: list[PlanStepView] = field(default_factory=list)
    completed_banner: bool = False
    activity: str = ""

    def upsert_step(
        self,
        *,
        step_id: str,
        step_index: int,
        title: str,
        status: str,
        reason: str | None = None,
    ) -> None:
        # 先按 step_id 更新；找不到再按序号改已有槽位，避免新 id 把整份清单换成一步
        if step_id:
            for s in self.steps:
                if s.step_id == step_id:
                    if title:
                        s.title = title
                    s.status = status
                    if reason is not None:
                        s.reason = reason or None
                    return
        for s in self.steps:
            if s.step_index == step_index:
                if step_id and s.step_id and step_id != s.step_id:
                    # 同序号但不同 id：忽略（replan 缩表），保留完整清单
                    return
                if title:
                    s.title = title
                s.status = status
                if reason is not None:
                    s.reason = reason or None
                if step_id and not s.step_id:
                    s.step_id = step_id
                return
        self.steps.append(
            PlanStepView(
                step_id=step_id,
                step_index=step_index,
                title=title,
                status=status,
                reason=reason or None,
            )
        )
        self.steps.sort(key=lambda x: x.step_index)


def plan_from_domain(plan: Plan) -> PlanView:
    view = PlanView(
        plan_id=plan.plan_id,
        session_id=plan.session_id,
        goal=plan.goal,
        status=plan.status.value,
        completed_banner=plan.status.value == "completed",
    )
    for step in sorted(plan.steps, key=lambda s: s.step_index):
        view.steps.append(
            PlanStepView(
                step_id=step.step_id,
                step_index=step.step_index,
                title=step.title,
                status=step.status.value,
                reason=getattr(step, "rationale", None),
            )
        )
    return view


def display_width(text: str) -> int:
    """终端显示宽度（CJK 计 2）。"""
    import unicodedata

    w = 0
    for ch in text:
        if unicodedata.east_asian_width(ch) in {"W", "F"}:
            w += 2
        else:
            w += 1
    return w


def truncate_display(text: str, max_width: int) -> str:
    if max_width <= 1:
        return "…"
    if display_width(text) <= max_width:
        return text
    out: list[str] = []
    w = 0
    for ch in text:
        cw = 2 if __import__("unicodedata").east_asian_width(ch) in {"W", "F"} else 1
        if w + cw > max_width - 1:
            break
        out.append(ch)
        w += cw
    return "".join(out) + "…"


def format_plan_panel(
    view: PlanView | Plan | None,
    *,
    numbered: bool = True,
    show_header: bool = True,
    show_status_line: bool = False,
    max_line_width: int | None = None,
    stable_height: bool = False,
) -> str:
    """纯文本 Plan 面板。

    每个步骤下方最多一行工具摘要（刷新覆盖）；stable_height 时带固定 footer。
    """
    if view is None:
        return "No active plan."
    if isinstance(view, Plan):
        view = plan_from_domain(view)
    if not view.steps and not view.plan_id:
        return "No active plan."

    width = max_line_width
    lines: list[str] = []
    if show_header:
        lines.append("Plan")
        if show_status_line and view.status:
            lines.append(f"Status: {view.status.upper().replace('_', ' ')}")
        lines.append("")
    else:
        lines.append("Plan")
        lines.append("")

    sorted_steps = sorted(view.steps, key=lambda s: s.step_index)
    active = next((s for s in sorted_steps if s.status == "in_progress"), None)
    activity_slots = 0
    for step in sorted_steps:
        glyph = STATUS_GLYPH.get(step.status, "○")
        title = " ".join((step.title or "").split())
        if numbered:
            row = f"{glyph} {step.step_index + 1}. {title}"
        else:
            row = f"{glyph} {title}"
        if width is not None:
            row = truncate_display(row, width)
        lines.append(row)

        hint = ""
        if step.tool_line.strip():
            hint = " ".join(step.tool_line.split())
        elif active is not None and step.step_id == active.step_id:
            hint = "…"
        elif step.status in {"failed", "blocked"} and step.reason:
            hint = " ".join(step.reason.split())

        if hint:
            act = f"     {hint}"
            if width is not None:
                act = truncate_display(act, width)
            elif len(hint) > 72:
                act = f"     {hint[:71]}…"
            lines.append(act)
            activity_slots += 1

    # Live 稳定高度：若当前没有任何工具行，仍占一行，避免光标行数跳动
    if stable_height and activity_slots == 0:
        lines.append("     ")

    if stable_height:
        lines.append("")
        if view.completed_banner or view.status == "completed":
            lines.append("✓ Plan completed")
        else:
            lines.append(" ")
    elif view.completed_banner or view.status == "completed":
        lines.append("")
        lines.append("✓ Plan completed")

    return "\n".join(lines)


def format_plan_strip(plan: Plan | None, *, max_title: int = 72) -> str:
    """兼容旧测试名。"""
    if plan is None:
        return ""
    return format_plan_panel(plan, numbered=True, show_header=True)


def plan_renderable(view: PlanView | Plan | None) -> Any:
    from rich.text import Text
    from rich.console import Group

    text = format_plan_panel(view, numbered=True, show_header=True)
    if not text or text == "No active plan.":
        return None
    parts: list[Text] = []
    for line in text.split("\n"):
        if line.startswith("●"):
            style = "cw.warn"
        elif line.startswith("✓"):
            style = "cw.ok"
        elif line.startswith("✗"):
            style = "cw.fail"
        elif line.startswith("Plan"):
            style = "cw.agent"
        elif line.startswith("     "):
            style = "cw.dim"
        else:
            style = "cw.dim"
        parts.append(Text(line, style=style))
    return Group(*parts)


def render_plan_strip(
    plan: Plan | None,
    *,
    output_fn: Callable[[str], None] = print,
    activity: str = "",  # noqa: ARG001 — 兼容旧签名
) -> None:
    text = format_plan_panel(
        plan,
        numbered=True,
        show_header=True,
        show_status_line=True,
    )
    if output_fn is print and get_theme().rich_enabled:
        renderable = plan_renderable(plan)
        if renderable is not None:
            make_console(width=terminal_width()).print(renderable)
            make_console().print()
            return
    output_fn(text)
    output_fn("")


# 兼容旧 API
def format_plan_status(plan: Plan | None, *, activity: str = "", max_title: int = 72) -> str:
    return format_plan_strip(plan, max_title=max_title)


def format_todo_checklist(plan: Plan | None, *, max_title: int = 72, max_items: int = 12) -> str:
    if plan is None:
        return ""
    view = plan_from_domain(plan)
    lines = []
    for i, step in enumerate(view.steps[:max_items]):
        glyph = STATUS_GLYPH.get(step.status, "○")
        prefix = "⎿ " if i == 0 else "  "
        lines.append(f"{prefix}{glyph} {step.title}")
    return "\n".join(lines)


def active_step_title(plan: Plan | None, *, fallback: str = "") -> str:
    if plan is None:
        return fallback
    for step in sorted(plan.steps, key=lambda s: s.step_index):
        if step.status == PlanStepStatus.IN_PROGRESS:
            return step.title or fallback
    return fallback
