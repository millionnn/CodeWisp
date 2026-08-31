"""CLI EventSink：Plan 下只挂一行工具摘要；最终回答真流式后再 MD 定稿。"""

from __future__ import annotations

import sys
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


class CliEventSink:
    """订阅 AgentEvent；Plan 写入对话，工具过程默认不打印。"""

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
        self._streamed_len = 0  # 已写到屏幕的 buf 前缀长度
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
        """只擦最终回答草稿行；绝不 CSI J（行数偏大时会把上方 Plan/历史清掉）。"""
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
        """Plan 已收尾 → 之后的 answer_delta 是最终回答，应真流式。"""
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
        """把新增正文写到屏幕（跟 LLM 真流式）。绝不停 Plan。"""
        if self._capture_answer or not delta:
            return
        if not self._answer_header_shown:
            self._stream_write_fn("\n")
            self._answer_header_shown = True
        self._stream_write_fn(delta)
        self._streamed_len = len(self._answer_buf)
        width = terminal_width()
        self._draft_rows = _visual_rows(self._answer_buf, width)
        if self._answer_header_shown:
            self._draft_rows += 1
        self.answer_streamed = True

    def _flush_unstreamed_answer(self) -> None:
        """把尚未写屏的 buf 尾部补流式写出。"""
        if self._capture_answer:
            return
        pending = self._answer_buf[self._streamed_len :]
        if pending:
            self._write_answer_delta(pending)

    def emit(self, event: AgentEvent) -> None:
        self.events.append(event)
        et = event.event_type

        if et in PLAN_EVENT_TYPES:
            self._stop_tool_spinner()
            self._renderer.handle_plan_event(event)
            # Plan 刚完成：若最终回答已在缓冲，冻结 Plan 后立刻吐已到的字
            if (
                et == "plan_completed"
                and self._answer_buf
                and not self.answer_streamed
            ):
                self._renderer.stop()
                self._flush_unstreamed_answer()
            return

        if et in {"tool_called", "tool_completed", "tool_failed"}:
            self._stop_tool_spinner()
            self._renderer.handle_tool_event(event)
            return

        if et == "answer_delta":
            delta = str((event.metadata or {}).get("delta") or "")
            if not delta:
                return
            self._answer_buf += delta
            # Plan 未完成：只缓冲（工具轮推测正文不写屏、不停 Plan）
            # Plan 已完成：先冻结 Plan（禁止再 cursor-up 改写），再真流式吐字
            # 否则光标已在回答区时 Plan 再上移改写，文字会往上盖住 Plan
            if self._plan_finished():
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
            # 回答已在流式：不要再 finalize 往下打一份 Plan
            if not self.answer_streamed:
                self._renderer.finalize_plan()
            self._renderer.stop()
            full = self._answer_buf
            if not full:
                return
            # 补上尚未流式的部分（Plan 在回答中途才标记完成的情况）
            if not self._capture_answer:
                self._flush_unstreamed_answer()
            if self._interactive and self._enable_markdown:
                if self.answer_streamed:
                    if full and not full.endswith("\n"):
                        self._stream_write_fn("\n")
                        self._draft_rows = (
                            _visual_rows(full + "\n", terminal_width()) + 1
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
