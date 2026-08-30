"""CLI 对 AgentEvent 轨迹的纯展示层（不编排 Agent、不访问 SQLite）。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.app.agent.state import AgentState, AgentStatus
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
    for key in (
        "path",
        "query",
        "pattern",
        "command",
        "expression",
        "old_string",
        "new_string",
        "content",
        "max_depth",
        "timeout",
    ):
        if key in arguments and arguments[key] is not None:
            val = arguments[key]
            if key == "command":
                lines.append(f"  $ {_short(val, 100)}")
            else:
                lines.append(f"  {key}: {_short(val)}")
    if not lines:
        # 兜底：最多展示 3 个键
        for i, (k, v) in enumerate(arguments.items()):
            if i >= 3:
                break
            lines.append(f"  {k}: {_short(v)}")
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
            return f"exit code: {out.get('exit_code')}"
        if "match_count" in out:
            return f"{out.get('match_count')} matches"
        if "line_count" in out:
            return f"{out.get('line_count')} lines"
        return _short(out, 100)
    text = str(out)
    # 多行输出：显示行数
    if "\n" in text:
        return f"{text.count(chr(10)) + 1} lines"
    return _short(text, 100)


def render_agent_trace(
    state: AgentState,
    run: AgentRun,
    *,
    output_fn: Callable[[str], None],
) -> None:
    """根据 AgentState.events 打印工具轨迹与终止摘要。"""
    events = list(state.events)
    pending_fail = False
    last_step_shown = 0

    for event in events:
        if event.event_type == "llm_called" and event.step != last_step_shown:
            output_fn(f"\nStep {event.step}")
            output_fn(f"  LLM  └─ {run.model_id}")
            last_step_shown = event.step

        if event.event_type == "tool_called":
            if pending_fail:
                output_fn("\n◇ Self-Correction")
                output_fn("  Agent observed a tool failure and continues.")
                pending_fail = False
            name = event.tool_name or "tool"
            output_fn(f"\n◇ {name}")
            args = (event.metadata or {}).get("arguments") or {}
            if isinstance(args, dict):
                for line in _format_tool_args(args):
                    output_fn(line)

        elif event.event_type == "tool_completed":
            name = event.tool_name or "tool"
            summary = _summarize_result(event.metadata or {})
            if summary:
                output_fn(f"✓ {name}")
                output_fn(f"  {summary}")
            else:
                output_fn(f"✓ {name}")

        elif event.event_type == "tool_failed":
            name = event.tool_name or "tool"
            summary = _summarize_result(event.metadata or {})
            output_fn(f"✗ {name}")
            if summary:
                output_fn(f"  {summary}")
            pending_fail = True

        elif event.event_type == "permission_required":
            output_fn("\nPermission required")
            output_fn(
                "  The agent requested an operation that requires approval."
            )
            err = (event.metadata or {}).get("error")
            if err:
                output_fn(f"  {err}")
            if event.tool_name:
                output_fn(f"  tool: {event.tool_name}")

    # 终止摘要
    tool_events = sum(
        1
        for e in events
        if e.event_type in {"tool_completed", "tool_failed"}
    )
    duration = None
    if events:
        duration = max(e.timestamp for e in events) - min(e.timestamp for e in events)

    output_fn("")
    if state.status == AgentStatus.COMPLETED:
        output_fn("Run completed")
    elif state.status == AgentStatus.MAX_STEPS:
        output_fn("Run stopped")
        output_fn("  Reason: maximum step budget reached")
    elif state.status == AgentStatus.PERMISSION_REQUIRED:
        output_fn("Run stopped")
        output_fn("  Reason: permission required")
    elif state.status == AgentStatus.FAILED:
        output_fn("Run failed")
        if state.error:
            output_fn(f"  Error: {state.error}")
    else:
        output_fn(f"Run ended ({state.status.value})")

    output_fn(f"  Steps       : {state.step}")
    output_fn(f"  Tool calls  : {tool_events}")
    output_fn(f"  Model       : {run.provider_id}/{run.model_id}")
    if state.termination_reason:
        output_fn(f"  Termination : {state.termination_reason}")
    if duration is not None and duration >= 0:
        output_fn(f"  Duration    : {duration:.1f}s")
