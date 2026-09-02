"""CLI Plan：一份固定高度清单，TTY 原地改 ✓ ● ○（不用 Rich Live，避免叠框）。"""

from __future__ import annotations

import sys
from collections.abc import Callable
from typing import Any

from backend.app.agent.events import AgentEvent
from backend.app.cli.render_plan import PlanStepView, PlanView, format_plan_panel, truncate_display
from backend.app.cli.render_trace import compact_trace_line
from backend.app.cli.theme import get_theme, terminal_width
from backend.app.cli.trace import render_live_event
from backend.app.context.plan_events import (
    PLAN_COMPLETED,
    PLAN_CREATED,
    PLAN_STEP_COMPLETED,
    PLAN_STEP_FAILED,
    PLAN_STEP_STARTED,
)

_ERASE_LINE = "\033[2K"
_CURSOR_UP = "\033[{n}A"


def compact_tool_activity(event: AgentEvent) -> str:
    """把一次工具调用压成一行，挂在当前 Plan 步骤下。"""
    name = event.tool_name or "tool"
    meta = event.metadata or {}
    nested = meta.get("metadata") if isinstance(meta.get("metadata"), dict) else {}
    display = str(meta.get("display") or (nested.get("display") if nested else "") or "")
    if name.startswith("mcp.") and not display:
        parts = name.split(".")
        if len(parts) >= 3:
            display = f"MCP · {parts[1]}.{'.'.join(parts[2:])}"
        else:
            display = f"MCP · {name}"
    label = display or name
    args = meta.get("arguments") or {}
    if not isinstance(args, dict):
        args = {}
    detail = ""
    if name.startswith("mcp."):
        for key in ("query", "q", "path", "uri", "name"):
            if args.get(key):
                detail = str(args[key])
                break
        if not detail and args:
            detail = str(next(iter(args.values())))[:40]
    elif name in {"read_file", "edit_file", "write_file"}:
        detail = str(args.get("path") or "")
    elif name == "search_code":
        detail = str(args.get("query") or args.get("pattern") or "")
    elif name == "run_command":
        cmd = str(args.get("command") or "")
        extra = args.get("args") or []
        if isinstance(extra, list) and extra:
            cmd = " ".join([cmd, *[str(a) for a in extra]]).strip()
        detail = cmd
    elif name == "list_files":
        detail = str(args.get("path") or ".")
    else:
        for key in ("path", "query", "pattern", "expression"):
            if args.get(key):
                detail = str(args[key])
                break
    if len(detail) > 64:
        detail = detail[:63] + "…"
    if event.event_type == "tool_failed":
        prefix = "✗"
    elif event.event_type == "tool_completed":
        prefix = "✓"
    else:
        prefix = "◇"
    return f"{prefix} {label} {detail}".rstrip()


def _colorize_plan_line(line: str) -> str:
    if not get_theme().color:
        return line
    # 青绿品牌色 + 琥珀进行中 + 翠绿完成 + 珊瑚失败（仅着色，不改文案）
    if line.startswith("●"):
        return f"\033[1;38;5;214m{line}\033[0m"
    if line.startswith("✓"):
        return f"\033[1;38;5;78m{line}\033[0m"
    if line.startswith("✗"):
        return f"\033[1;38;5;203m{line}\033[0m"
    if line.startswith("Plan"):
        return f"\033[1;38;5;80m{line}\033[0m"
    if line.startswith("○"):
        return f"\033[2;38;5;105m{line}\033[0m"
    if line.startswith("     "):
        return _colorize_trace_or_tool_line(line)
    return f"\033[2;38;5;245m{line}\033[0m"


def _is_trace_content(stripped: str) -> bool:
    if not stripped or stripped == "…":
        return False
    if stripped[0] in {"✅", "❌"}:
        return True
    if stripped[0] in "◇✓✗":
        return False
    return "+" in stripped and "." in stripped.split()[0]


def _colorize_trace_or_tool_line(line: str) -> str:
    stripped = line.lstrip(" ")
    indent = line[: len(line) - len(stripped)]
    if _is_trace_content(stripped):
        if stripped.startswith("✅"):
            return f"{indent}\033[1;38;5;78m{stripped}\033[0m"
        if stripped.startswith("❌"):
            return f"{indent}\033[1;38;5;203m{stripped}\033[0m"
        # 文件变更：path 高亮 + 绿+/红-
        parts = stripped.split(None, 1)
        path = parts[0]
        stats = parts[1] if len(parts) > 1 else ""
        out = f"{indent}\033[1;38;5;117m{path}\033[0m"
        if stats:
            out += f" \033[2;38;5;245m{stats}\033[0m"
        return out
    return _colorize_tool_activity_line(line)


def _colorize_tool_activity_line(line: str) -> str:
    """Plan 步骤下工具行：符号 / 工具名 / 详情分色。"""
    stripped = line.lstrip(" ")
    indent = line[: len(line) - len(stripped)]
    if not stripped or stripped.strip() in {"", "…"}:
        return f"\033[2;38;5;245m{line}\033[0m"

    parts = stripped.split(None, 2)
    glyph = parts[0]
    name = parts[1] if len(parts) > 1 else ""
    detail = parts[2] if len(parts) > 2 else ""

    if glyph == "✓":
        g = "\033[1;38;5;78m"  # green
    elif glyph == "✗":
        g = "\033[1;38;5;203m"  # red
    elif glyph == "◇":
        g = "\033[1;38;5;80m"  # teal
    else:
        g = "\033[2;38;5;245m"

    out = f"{indent}{g}{glyph}\033[0m"
    if name:
        out += f" \033[1;38;5;117m{name}\033[0m"  # bright sky tool name
    if detail:
        out += f" \033[2;38;5;245m{detail}\033[0m"
    return out


class CliLiveRenderer:
    """Plan 写入对话；可选打印完整 Tool Trace。"""

    def __init__(
        self,
        *,
        output_fn: Callable[[str], None],
        interactive: bool,
        model_id: str | None = None,
        show_tool_trace: bool = False,
    ) -> None:
        self._output_fn = output_fn
        self._interactive = interactive
        self._model_id = model_id
        self._show_tool_trace = show_tool_trace
        self.plan_view: PlanView | None = None
        self._pending_fail = False
        self._last_step = 0
        self._last_panel_text = ""
        self._activity = ""
        self._plan_rows = 0
        self._plan_live = False
        self._stopped = False

    def set_model_id(self, model_id: str | None) -> None:
        self._model_id = model_id

    def set_show_tool_trace(self, show: bool) -> None:
        self._show_tool_trace = show

    def is_stopped(self) -> bool:
        return self._stopped

    def stop(self) -> None:
        """停止原地改写；当前清单留在滚动区。"""
        self._plan_live = False
        self._plan_rows = 0
        self._stopped = True

    def freeze(self) -> None:
        self.stop()

    def finalize_plan(self) -> None:
        """回答定稿前强制刷一次最新 Plan（通常已是全部 ✓）。"""
        if self.plan_view is None:
            return
        self._stopped = False
        self._paint_plan(force=True)

    def handle_plan_event(self, event: AgentEvent) -> None:
        meta = event.metadata or {}
        et = event.event_type

        if et == PLAN_CREATED:
            self._on_plan_created(meta)
            return

        if self.plan_view is None:
            self.plan_view = PlanView(
                plan_id=str(meta.get("plan_id") or ""),
                session_id=str(meta.get("session_id") or ""),
            )

        if et in {PLAN_STEP_STARTED, PLAN_STEP_COMPLETED, PLAN_STEP_FAILED}:
            status = str(meta.get("status") or "pending")
            reason: str | None
            if et == PLAN_STEP_STARTED:
                status = "in_progress"
                for s in self.plan_view.steps:
                    if s.status == "in_progress":
                        s.status = "pending"
                # 保留上一工具活动行；不要清成「…」
                reason = ""
            elif et == PLAN_STEP_COMPLETED:
                status = str(meta.get("status") or "completed")
                reason = ""
            else:
                status = str(meta.get("status") or "failed")
                reason = meta.get("reason")
            self.plan_view.upsert_step(
                step_id=str(meta.get("step_id") or ""),
                step_index=int(meta.get("step_index") or 0),
                title=str(meta.get("title") or ""),
                status=status,
                reason=reason,
            )
            self.plan_view.status = "in_progress"
            self.plan_view.activity = self._activity
            self._paint_plan()
            return

        if et == PLAN_COMPLETED:
            self.plan_view.status = str(meta.get("status") or "completed")
            self.plan_view.completed_banner = True
            for raw in meta.get("steps") or []:
                if isinstance(raw, dict):
                    self.plan_view.upsert_step(
                        step_id=str(raw.get("step_id") or ""),
                        step_index=int(raw.get("step_index") or 0),
                        title=str(raw.get("title") or ""),
                        status=str(raw.get("status") or "completed"),
                    )
            self.plan_view.activity = self._activity
            self._paint_plan(force=True)
            # 不在此处 stop：Agent 常在 plan_completed 之后继续调工具
            return

    def _resolve_tool_step(self) -> PlanStepView | None:
        """工具行挂到哪一步：优先 in_progress；Plan 已全绿则填第一个空槽。"""
        if self.plan_view is None:
            return None
        steps = sorted(self.plan_view.steps, key=lambda s: s.step_index)
        active = next((s for s in steps if s.status == "in_progress"), None)
        if active is not None:
            return active
        for step in steps:
            if step.status in {"completed", "failed", "blocked", "skipped"}:
                if not step.tool_line.strip():
                    return step
        return steps[-1] if steps else None

    def handle_tool_event(self, event: AgentEvent) -> None:
        """当前 in_progress 步骤下只刷新一行工具摘要；Plan 底栏 trace 单行刷新。"""
        self._activity = compact_tool_activity(event)
        trace = compact_trace_line(event)
        if self._show_tool_trace:
            self.stop()
            self._pending_fail, self._last_step = render_live_event(
                event,
                output_fn=self._output_fn,
                model_id=self._model_id,
                pending_fail=self._pending_fail,
                last_step_shown=self._last_step,
            )
            return

        if self.plan_view is None or self._stopped:
            return

        if trace:
            self.plan_view.trace_line = trace
        self.plan_view.activity = self._activity
        # 完成信号只推进步骤，不覆盖该步已挂的工具摘要行
        if event.tool_name == "complete_plan_step":
            self._paint_plan()
            return
        target = self._resolve_tool_step()
        if target is not None:
            target.tool_line = self._activity  # 覆盖刷新，不堆多行
        self._paint_plan()

    def _on_plan_created(self, meta: dict[str, Any]) -> None:
        pid = str(meta.get("plan_id") or "")
        sid = str(meta.get("session_id") or "")
        # 新一轮：在下方新开一块，不回头改历史
        if self._stopped:
            self._stopped = False
            self._plan_live = False
            self._plan_rows = 0
            self._last_panel_text = ""
            self.plan_view = None
        if (
            self.plan_view is not None
            and pid
            and self.plan_view.plan_id
            and pid != self.plan_view.plan_id
        ):
            self._plan_live = False
            self._plan_rows = 0
            self._last_panel_text = ""
            self.plan_view = None

        if self.plan_view is None:
            self.plan_view = PlanView(
                plan_id=pid,
                session_id=sid,
                goal=str(meta.get("goal") or ""),
                status=str(meta.get("status") or "in_progress"),
            )
        else:
            if pid:
                self.plan_view.plan_id = pid
            if sid:
                self.plan_view.session_id = sid
            if meta.get("goal"):
                self.plan_view.goal = str(meta.get("goal"))
            self.plan_view.status = str(meta.get("status") or self.plan_view.status)

        for raw in meta.get("steps") or []:
            if not isinstance(raw, dict):
                continue
            self.plan_view.upsert_step(
                step_id=str(raw.get("step_id") or ""),
                step_index=int(raw.get("step_index") or 0),
                title=str(raw.get("title") or ""),
                status=str(raw.get("status") or "pending"),
            )
        self._activity = ""
        self.plan_view.activity = ""
        self.plan_view.trace_line = ""
        self._stopped = False
        self._paint_plan(force=True)

    def _paint_plan(self, *, force: bool = False) -> None:
        if self.plan_view is None or self._stopped:
            return
        width = terminal_width()
        text = format_plan_panel(
            self.plan_view,
            numbered=True,
            show_header=True,
            show_status_line=False,
            max_line_width=max(40, width - 2),
            stable_height=True,
        )
        if not force and text == self._last_panel_text:
            return
        self._last_panel_text = text

        use_inplace = self._interactive and sys.stdout.isatty()
        if use_inplace:
            self._rewrite_plan_block(text)
            return

        # 非 TTY / 测试：只在内容变化时追加一份，避免每次 tool 都叠框
        self._output_fn("")
        self._output_fn(text)
        self._output_fn("")

    def _rewrite_plan_block(self, text: str) -> None:
        """固定行数原地改写；只用 2K 清行，绝不 CSI J。"""
        width = max(40, terminal_width() - 1)
        raw_lines = text.split("\n")
        lines = [
            _colorize_plan_line(truncate_display(line, width)) for line in raw_lines
        ]
        n = len(lines)
        out = sys.stdout
        if self._plan_live and self._plan_rows > 0:
            # 行数必须不变（stable_height）；若变了也按新高度写，多出的行清掉
            out.write(_CURSOR_UP.format(n=self._plan_rows))
            for line in lines:
                out.write(f"{_ERASE_LINE}{line}\n")
            extra = self._plan_rows - n
            if extra > 0:
                for _ in range(extra):
                    out.write(f"{_ERASE_LINE}\n")
                out.write(_CURSOR_UP.format(n=extra))
        else:
            out.write("\n")
            for line in lines:
                out.write(f"{line}\n")
        out.flush()
        self._plan_rows = n
        self._plan_live = True
