"""CLI EventSink：Plan Live 与最终回答解耦；Plan 收尾后冻结，回答在确认终稿后再流式。"""

from __future__ import annotations

import sys
import time
from collections.abc import Callable
from typing import Any

from backend.app.agent.events import AgentEvent
from backend.app.cli.live_renderer import CliLiveRenderer
from backend.app.cli.render_md import render_markdown
from backend.app.cli.theme import get_theme, terminal_width
from backend.app.cli.trace import render_live_event
from backend.app.context.plan_events import PLAN_EVENT_TYPES

_QUIET_PROCESS = frozenset(
    {
        "llm_started",
        "llm_called",
        "tool_called",
        "tool_completed",
        "tool_failed",
        "command_output_line",
        "agent_started",
    }
)

_ANSWER_HEADER = "✦ Final Answer"


class CliEventSink:
    """订阅 AgentEvent；Plan 写入对话，工具过程默认挂在当前步骤下。"""

    def __init__(
        self,
        *,
        output_fn: Callable[[str], None] | None = None,
        stream_write_fn: Callable[[str], None] | None = None,
        model_id: str | None = None,
        enable_spinner: bool = True,
        enable_markdown: bool = True,
        plan_provider: Callable[[], Any] | None = None,
        show_todos: bool = True,  # noqa: ARG002
        quiet_tools: bool | None = None,
        show_tool_trace: bool | None = None,
    ) -> None:
        self._output_fn = output_fn or print
        self._model_id = model_id
        self._pending_fail = False
        self._last_step = 0
        self.answer_streamed = False
        self._answer_header_shown = False
        self._answer_buf = ""
        self._draft_rows = 0
        self._streamed_len = 0
        # Plan 提前完成但 agent 仍在跑工具时：禁止把推测正文当 Final Answer 刷屏
        self._hold_answer_until_done = False
        self.events: list[AgentEvent] = []
        self._enable_spinner = enable_spinner
        self._enable_markdown = enable_markdown
        self._plan_provider = plan_provider
        self._status = None
        if show_tool_trace is not None:
            show_trace = bool(show_tool_trace)
        elif quiet_tools is not None:
            show_trace = not bool(quiet_tools)
        else:
            show_trace = False
        self._show_tool_trace = show_trace
        self._interactive = (
            (output_fn is None or output_fn is print)
            and sys.stdout.isatty()
            and get_theme().rich_enabled
        )

        self._renderer = CliLiveRenderer(
            output_fn=self._output_fn,
            interactive=self._interactive and self._enable_spinner,
            model_id=model_id,
            show_tool_trace=self._show_tool_trace,
        )

        if stream_write_fn is not None:
            self._stream_write_fn = stream_write_fn
            self._capture_answer = False
        elif self._interactive:
            self._stream_write_fn = _default_stream_write
            self._capture_answer = False
        else:
            self._stream_write_fn = self._buffer_answer
            self._capture_answer = True

    def set_model_id(self, model_id: str) -> None:
        self._model_id = model_id
        self._renderer.set_model_id(model_id)

    def set_plan_provider(self, provider: Callable[[], Any] | None) -> None:
        self._plan_provider = provider

    def set_show_todos(self, show: bool) -> None:  # noqa: ARG002
        return

    def _buffer_answer(self, text: str) -> None:
        self._answer_buf += text

    def _stop_tool_spinner(self) -> None:
        if self._status is not None:
            try:
                self._status.stop()
            except Exception:  # noqa: BLE001
                pass
            self._status = None

    def _clear_streamed_draft(self) -> None:
        """只擦最终回答草稿行；绝不 CSI J。"""
        if not self._interactive or not self.answer_streamed:
            return
        rows = max(1, self._draft_rows)
        out = sys.stdout
        out.write(f"\033[{rows}A")
        for _ in range(rows):
            out.write("\033[2K\n")
        out.write(f"\033[{rows}A")
        out.flush()
        self._draft_rows = 0

    def _plan_finished(self) -> bool:
        view = self._renderer.plan_view
        if view is None:
            return True
        if view.completed_banner or view.status == "completed":
            return True
        if view.steps and all(
            s.status in {"completed", "skipped", "cancelled"} for s in view.steps
        ):
            return True
        return False

    def _write_answer_delta(self, delta: str) -> None:
        """把新增正文写到屏幕。调用前须已 freeze Plan。"""
        if self._capture_answer or not delta:
            return
        if not self._answer_header_shown:
            self._stream_write_fn("\n")
            if self._interactive and get_theme().color:
                self._stream_write_fn(f"\033[1;36m{_ANSWER_HEADER}\033[0m")
            else:
                self._stream_write_fn(_ANSWER_HEADER)
            self._stream_write_fn("\n")
            self._answer_header_shown = True
        self._stream_write_fn(delta)
        self._streamed_len = len(self._answer_buf)
        width = terminal_width()
        prefix = f"\n{_ANSWER_HEADER}\n" if self._answer_header_shown else ""
        self._draft_rows = _visual_rows(prefix + self._answer_buf, width)
        self.answer_streamed = True

    def _flush_unstreamed_answer(self, *, typewriter: bool = False) -> None:
        if self._capture_answer:
            return
        pending = self._answer_buf[self._streamed_len :]
        if not pending:
            return
        if typewriter and self._interactive and len(pending) > 1:
            # 终稿确认后再吐字：避免 Plan 完成后工具轮推测正文抢写/上擦
            chunk = 2
            delay = min(0.012, 0.8 / max(len(pending), 1))
            for i in range(0, len(pending), chunk):
                self._write_answer_delta(pending[i : i + chunk])
                time.sleep(delay)
        else:
            self._write_answer_delta(pending)

    def emit(self, event: AgentEvent) -> None:
        self.events.append(event)
        et = event.event_type

        if et in PLAN_EVENT_TYPES:
            self._stop_tool_spinner()
            self._renderer.handle_plan_event(event)
            if et == "plan_completed":
                # 冻结清单：之后禁止 cursor-up 改写（否则会擦掉下方内容）
                self._renderer.stop()
                # 不立刻 flush 缓冲正文——可能仍是工具轮推测文字
                # hold 仅在「完成后又出现工具」时打开，以便纯最终回答仍可真流式
            return

        if et in {"tool_called", "tool_completed", "tool_failed"}:
            self._stop_tool_spinner()
            if self._plan_finished():
                # Plan 已全绿但 agent 还在干活：推迟 Final Answer，避免推测正文上擦
                self._hold_answer_until_done = True
            self._renderer.handle_tool_event(event)
            return

        if et == "answer_delta":
            delta = str((event.metadata or {}).get("delta") or "")
            if not delta:
                return
            self._answer_buf += delta
            # Plan 未完成：只缓冲
            # Plan 已完成但仍可能继续调工具：继续只缓冲（hold），等 agent_completed
            # 仅当 Plan 已完成且中间没有「完成后又干活」时才真流式
            if self._plan_finished() and not self._hold_answer_until_done:
                if not self.answer_streamed:
                    self._renderer.stop()
                self._write_answer_delta(delta)
            return

        if et == "answer_discard":
            if self.answer_streamed and self._interactive:
                self._clear_streamed_draft()
            self._answer_buf = ""
            self._answer_header_shown = False
            self.answer_streamed = False
            self._draft_rows = 0
            self._streamed_len = 0
            return

        if et == "agent_completed":
            self._stop_tool_spinner()
            if not self.answer_streamed:
                # Plan 若从未 finalize（已 stop），不要再 cursor-up；仅未冻结时补打
                if not self._renderer.is_stopped():
                    self._renderer.finalize_plan()
            self._renderer.stop()
            full = self._answer_buf
            if not full:
                self._hold_answer_until_done = False
                return
            if not self._capture_answer:
                self._flush_unstreamed_answer(
                    typewriter=bool(self._hold_answer_until_done or not self.answer_streamed)
                )
            if self._interactive and self._enable_markdown:
                if self.answer_streamed:
                    if full and not full.endswith("\n"):
                        self._stream_write_fn("\n")
                        full_for_rows = full + "\n"
                    else:
                        full_for_rows = full
                    prefix = f"\n{_ANSWER_HEADER}\n"
                    self._draft_rows = _visual_rows(
                        prefix + full_for_rows, terminal_width()
                    )
                    self._clear_streamed_draft()
                render_markdown(full, force_plain=False)
                self.answer_streamed = True
            elif self._capture_answer:
                self._output_fn("\nCodeWisp:")
                render_markdown(full, output_fn=self._output_fn, force_plain=True)
                self.answer_streamed = True
            else:
                if not self.answer_streamed:
                    self._stream_write_fn("\n")
                    self._stream_write_fn(full)
                self._stream_write_fn("\n")
                self.answer_streamed = True
            self._answer_buf = ""
            self._answer_header_shown = False
            self._streamed_len = 0
            self._hold_answer_until_done = False
            return

        if et == "permission_requested":
            self._stop_tool_spinner()
            self._renderer.stop()
            self._pending_fail, self._last_step = render_live_event(
                event,
                output_fn=self._output_fn,
                model_id=self._model_id,
                pending_fail=self._pending_fail,
                last_step_shown=self._last_step,
            )
            return

        if et in _QUIET_PROCESS and not self._show_tool_trace:
            return

        self._pending_fail, self._last_step = render_live_event(
            event,
            output_fn=self._output_fn,
            model_id=self._model_id,
            pending_fail=self._pending_fail,
            last_step_shown=self._last_step,
            stream_write_fn=None if self._capture_answer else self._stream_write_fn,
        )


def _char_display_width(ch: str) -> int:
    import unicodedata

    if unicodedata.east_asian_width(ch) in {"W", "F"}:
        return 2
    return 1


def _visual_rows(text: str, width: int) -> int:
    """按终端列宽估算行数（CJK 计 2），避免清草稿时上移过多误擦 Plan。"""
    if not text:
        return 0
    w = max(1, width)
    rows = 0
    for line in text.split("\n"):
        if line == "":
            rows += 1
            continue
        col = 0
        line_rows = 1
        for ch in line:
            cw = _char_display_width(ch)
            if col + cw > w:
                line_rows += 1
                col = cw
            else:
                col += cw
        rows += line_rows
    return rows


def _default_stream_write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()
