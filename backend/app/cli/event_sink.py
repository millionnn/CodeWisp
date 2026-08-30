"""CLI 实时 EventSink：过程事件 + 回答流式(S1) + 工具 Spinner。"""

from __future__ import annotations

import sys
from collections.abc import Callable

from backend.app.agent.events import AgentEvent
from backend.app.cli.render_md import render_markdown
from backend.app.cli.theme import get_theme, make_console
from backend.app.cli.trace import render_live_event

#cli接受到时间之后，怎么打印
#调用工具的步骤行为单位打印，最终回答流式打印输出
class CliEventSink:
    """Agent 执行过程中即时打印事件。

    最终回答（S1）：先流式纯文本草稿 → 结束后按可视行数清除草稿 → Markdown 重绘。
    仅最终无 tool_calls 的回合会推送 answer_delta（由 LLMClient 保证）。
    """

    def __init__(
        self,
        *,
        output_fn: Callable[[str], None] | None = None,
        stream_write_fn: Callable[[str], None] | None = None,
        model_id: str | None = None,
        enable_spinner: bool = True,
        enable_markdown: bool = True,
    ) -> None:
        self._output_fn = output_fn or print
        self._model_id = model_id
        self._pending_fail = False
        self._last_step = 0
        self.answer_streamed = False
        self._answer_header_shown = False
        self._answer_buf = ""
        self._draft_rows = 0
        self.events: list[AgentEvent] = []
        self._enable_spinner = enable_spinner
        self._enable_markdown = enable_markdown
        self._status = None
        self._interactive = (
            output_fn is None or output_fn is print
        ) and get_theme().rich_enabled

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

    def _buffer_answer(self, text: str) -> None:
        self._answer_buf += text

    def _stop_spinner(self) -> None:
        if self._status is not None:
            try:
                self._status.stop()
            except Exception:  # noqa: BLE001
                pass
            self._status = None

    def _start_spinner(self, name: str) -> None:
        if not self._enable_spinner or not self._interactive:
            return
        self._stop_spinner()
        console = make_console()
        self._status = console.status(f"[cw.dim]{name}…[/]", spinner="dots")
        self._status.start()

    def _clear_streamed_draft(self) -> None:
        """按草稿占用的可视行数上移并清除（比 DECSC/DECRC 更可靠）。"""
        if not self._interactive or not self.answer_streamed:
            return
        rows = max(1, self._draft_rows)
        # 上移 rows 行到草稿起点，再清除到屏末
        sys.stdout.write(f"\033[{rows}A\033[J")
        sys.stdout.flush()
        self._draft_rows = 0

    def emit(self, event: AgentEvent) -> None:
        self.events.append(event)

        if event.event_type == "tool_called":
            self._stop_spinner()
            name = event.tool_name or "tool"
            self._pending_fail, self._last_step = render_live_event(
                event,
                output_fn=self._output_fn,
                model_id=self._model_id,
                pending_fail=self._pending_fail,
                last_step_shown=self._last_step,
            )
            self._start_spinner(name)
            return

        if event.event_type in {"tool_completed", "tool_failed"}:
            self._stop_spinner()

        if event.event_type == "answer_delta":
            delta = str((event.metadata or {}).get("delta") or "")
            if not delta:
                return
            if not self._answer_header_shown:
                if self._interactive:
                    self._stream_write_fn("\n")
                else:
                    self._output_fn("")
                self._answer_header_shown = True
            self._stream_write_fn(delta)
            self._answer_buf += delta
            width = get_theme().width
            self._draft_rows = _visual_rows(self._answer_buf, width)
            if self._answer_header_shown:
                self._draft_rows += 1
            self.answer_streamed = True
            return

        if event.event_type == "answer_discard":
            # 工具回合：丢掉已流式的中间正文，避免残留在 Trace 上方
            if self.answer_streamed and self._interactive:
                if self._answer_buf and not self._answer_buf.endswith("\n"):
                    self._stream_write_fn("\n")
                    self._draft_rows = _visual_rows(
                        self._answer_buf + "\n", get_theme().width
                    ) + (1 if self._answer_header_shown else 0)
                self._clear_streamed_draft()
            self._answer_buf = ""
            self._answer_header_shown = False
            self.answer_streamed = False
            self._draft_rows = 0
            return

        if event.event_type == "agent_completed":
            self._stop_spinner()
            if self.answer_streamed:
                full = self._answer_buf
                if self._interactive and self._enable_markdown:
                    # 草稿末尾可能没有换行；先补一行再按行数擦除
                    if full and not full.endswith("\n"):
                        self._stream_write_fn("\n")
                        self._draft_rows = _visual_rows(full + "\n", get_theme().width) + 1
                    self._clear_streamed_draft()
                    render_markdown(full, force_plain=False)
                elif self._capture_answer:
                    self._output_fn("\nCodeWisp:")
                    render_markdown(full, output_fn=self._output_fn, force_plain=True)
                else:
                    self._stream_write_fn("\n")
                self._answer_buf = ""
                self._answer_header_shown = False

        self._pending_fail, self._last_step = render_live_event(
            event,
            output_fn=self._output_fn,
            model_id=self._model_id,
            pending_fail=self._pending_fail,
            last_step_shown=self._last_step,
            stream_write_fn=None if self._capture_answer else self._stream_write_fn,
        )


def _visual_rows(text: str, width: int) -> int:
    """估算文本在终端中占用的行数（含自动折行）。"""
    if not text:
        return 0
    w = max(1, width)
    rows = 0
    for line in text.split("\n"):
        if line == "":
            rows += 1
            continue
        # 粗略按显示宽度：CJK 等宽估算为 2 列过重，这里按字符数近似
        rows += max(1, (len(line) + w - 1) // w)
    if text.endswith("\n"):
        # split 已计空行；endswith 时最后多一个空段已计入
        pass
    return rows


def _default_stream_write(text: str) -> None:
    sys.stdout.write(text)
    sys.stdout.flush()
