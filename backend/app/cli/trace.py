"""CLI Trace 渲染（颜色 / 符号；NO_COLOR 时纯文本）。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.app.agent.events import AgentEvent
from backend.app.agent.state import AgentState, AgentStatus
from backend.app.cli.theme import get_theme, style
from backend.app.session.models import AgentRun


def _short(value: Any, limit: int = 80) -> str:
    text = str(value) if value is not None else ""
    text = text.replace("\n", " ").strip()
    if len(text) > limit:
        return text[: limit - 1] + "…"
    return text


def _format_tool_args(arguments: dict[str, Any] | None) -> list[str]:
    if not arguments:
        return []
    lines: list[str] = []
    if "command" in arguments and arguments.get("command") is not None:
        cmd = str(arguments.get("command") or "").strip()
        raw_args = arguments.get("args") or []
        if isinstance(raw_args, list) and raw_args:
            argv = " ".join([cmd, *[str(a) for a in raw_args]]).strip()
        else:
            argv = cmd
        lines.append(f"    $ {_short(argv, 120)}")
    for key in (
        "path",
        "query",
        "pattern",
        "expression",
        "old_string",
        "new_string",
        "content",
        "max_depth",
        "timeout",
        "cwd",
    ):
        if key in arguments and arguments[key] is not None:
            lines.append(f"    {key:<10} {_short(arguments[key])}")
    if not lines:
        for i, (k, v) in enumerate(arguments.items()):
            if i >= 3:
                break
            lines.append(f"    {k:<10} {_short(v)}")
    return lines


def _summarize_result(meta: dict[str, Any]) -> str | None:
    if not meta:
        return None
    if meta.get("error"):
        return _short(meta.get("error"), 120)
    out = meta.get("output")
    if out is None:
        return None
    if isinstance(out, list):
        return f"{len(out)} items"
    if isinstance(out, dict):
        if "exit_code" in out:
            parts = [f"exit {out.get('exit_code')}"]
            if out.get("timed_out"):
                parts.append("timed out")
            stderr = out.get("stderr") or ""
            if stderr and not out.get("success", True):
                parts.append(_short(stderr, 60))
            return " · ".join(parts)
        if "match_count" in out:
            return f"{out.get('match_count')} matches"
        if "line_count" in out:
            return f"{out.get('line_count')} lines"
        return _short(out, 100)
    text = str(out)
    if "\n" in text:
        return f"{text.count(chr(10)) + 1} lines"
    return _short(text, 100)


def _plain(output_fn: Callable[[str], None]) -> bool:
    return output_fn is not print or not get_theme().rich_enabled


def _out(output_fn: Callable[[str], None], text: str, sty: str | None = None) -> None:
    if sty and not _plain(output_fn):
        output_fn(style(text, sty))
    else:
        output_fn(text)


def render_live_event(
    event: AgentEvent,
    *,
    output_fn: Callable[[str], None],
    model_id: str | None = None,
    pending_fail: bool = False,
    last_step_shown: int = 0,
    stream_write_fn: Callable[[str], None] | None = None,
) -> tuple[bool, int]:
    """渲染单条事件（实时）。返回 (pending_fail, last_step_shown)。"""
    if event.event_type in {"llm_started", "llm_called"} and event.step != last_step_shown:
        _out(output_fn, f"\n  Step {event.step}", "cw.step")
        mid = model_id or (event.metadata or {}).get("model_id") or "llm"
        _out(output_fn, f"  ┊  LLM  {mid}", "cw.dim")
        last_step_shown = event.step
        if event.event_type == "llm_called":
            return pending_fail, last_step_shown

    if event.event_type == "tool_called":
        if pending_fail:
            _out(output_fn, "\n  ── Self-Correction ──", "cw.warn")
            _out(output_fn, "  ┊  Observed a failure; continuing.", "cw.dim")
            pending_fail = False
        name = event.tool_name or "tool"
        _out(output_fn, f"\n  ◇ {name}", "cw.info")
        args = (event.metadata or {}).get("arguments") or {}
        if isinstance(args, dict):
            for line in _format_tool_args(args):
                _out(output_fn, line, "cw.dim")

    elif event.event_type == "tool_completed":
        name = event.tool_name or "tool"
        summary = _summarize_result(event.metadata or {})
        _out(output_fn, f"  ✓ {name}", "cw.ok")
        if summary:
            _out(output_fn, f"     {summary}", "cw.dim")

    elif event.event_type == "tool_failed":
        name = event.tool_name or "tool"
        summary = _summarize_result(event.metadata or {})
        _out(output_fn, f"  ✗ {name}", "cw.fail")
        if summary:
            _out(output_fn, f"     {summary}", "cw.dim")
        pending_fail = True

    elif event.event_type == "command_output_line":
        stream = (event.metadata or {}).get("stream") or "stdout"
        line = str((event.metadata or {}).get("line") or "").rstrip("\n")
        prefix = "     │ " if stream == "stdout" else "     ‼ "
        sty = "cw.dim" if stream == "stdout" else "cw.warn"
        _out(output_fn, f"{prefix}{line}", sty)

    elif event.event_type == "permission_requested":
        _out(output_fn, "\n  ⚠  Permission requested", "cw.warn")
        cmd = (event.metadata or {}).get("command")
        if cmd:
            args = (event.metadata or {}).get("args") or []
            argv = " ".join([str(cmd), *[str(a) for a in args]]).strip()
            _out(output_fn, f"     $ {argv}", "cw.cmd")

    elif event.event_type == "permission_resolved":
        decision = (event.metadata or {}).get("decision")
        sty = "cw.ok" if decision == "allow" else "cw.fail"
        _out(output_fn, f"  ✓ Permission {decision}", sty)

    elif event.event_type == "permission_required":
        _out(output_fn, "\n  Permission required", "cw.warn")
        _out(
            output_fn,
            "  The agent requested an operation that requires approval.",
            "cw.dim",
        )
        err = (event.metadata or {}).get("error")
        if err:
            _out(output_fn, f"  {err}", "cw.dim")

    elif event.event_type == "revert_started":
        target = (event.metadata or {}).get("target_type")
        tid = (event.metadata or {}).get("target_id")
        _out(output_fn, f"\n  ↺  Revert started ({target} {tid})", "cw.warn")

    elif event.event_type == "snapshot_created":
        reason = (event.metadata or {}).get("reason")
        sid = (event.metadata or {}).get("snapshot_id")
        _out(output_fn, f"  ○  Snapshot [{reason}] {sid}", "cw.dim")

    elif event.event_type == "revert_completed":
        _out(output_fn, "  ✓  Revert completed", "cw.ok")

    elif event.event_type == "revert_failed":
        if (event.metadata or {}).get("denied"):
            _out(output_fn, "  ✗  Revert denied", "cw.fail")
        else:
            _out(output_fn, "  ✗  Revert failed", "cw.fail")

    elif event.event_type == "answer_delta":
        delta = (event.metadata or {}).get("delta") or ""
        if delta and stream_write_fn is not None:
            stream_write_fn(delta)

    return pending_fail, last_step_shown


def render_agent_trace(
    state: AgentState,
    run: AgentRun,
    *,
    output_fn: Callable[[str], None],
) -> None:
    events = list(state.events)
    pending_fail = False
    last_step_shown = 0
    for event in events:
        pending_fail, last_step_shown = render_live_event(
            event,
            output_fn=output_fn,
            model_id=run.model_id,
            pending_fail=pending_fail,
            last_step_shown=last_step_shown,
        )
    render_run_summary(state, run, output_fn=output_fn)


def render_run_summary(
    state: AgentState,
    run: AgentRun,
    *,
    output_fn: Callable[[str], None],
) -> None:
    events = list(state.events)
    tool_events = sum(
        1 for e in events if e.event_type in {"tool_completed", "tool_failed"}
    )
    duration = None
    if events:
        duration = max(e.timestamp for e in events) - min(e.timestamp for e in events)

    if state.status == AgentStatus.COMPLETED:
        label = "✓  completed"
        sty = "cw.ok"
    elif state.status == AgentStatus.MAX_STEPS:
        label = "○  stopped (max steps)"
        sty = "cw.warn"
    elif state.status == AgentStatus.PERMISSION_REQUIRED:
        label = "○  stopped (permission)"
        sty = "cw.warn"
    elif state.status == AgentStatus.FAILED:
        label = "✗  failed"
        sty = "cw.fail"
    else:
        label = f"○  ended ({state.status.value})"
        sty = "cw.dim"

    parts = [label, f"{state.step} steps", f"{tool_events} tools"]
    parts.append(f"{run.provider_id}/{run.model_id}")
    if duration is not None and duration >= 0:
        parts.append(f"{duration:.1f}s")
    line = " · ".join(parts)
    output_fn("")
    _out(output_fn, f"  {line}", sty)
    if state.status == AgentStatus.FAILED and state.error:
        _out(output_fn, f"     {state.error}", "cw.fail")
