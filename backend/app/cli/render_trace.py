"""Plan 底栏 trace：文件变更与命令结果（单行刷新）。"""

from __future__ import annotations

from pathlib import Path

from backend.app.agent.events import AgentEvent


def _basename(path: str) -> str:
    text = (path or "").strip()
    if not text:
        return "file"
    return Path(text).name or text


def _line_count(text: str) -> int:
    if not text:
        return 0
    parts = text.splitlines()
    return len(parts) if parts else 1


def compact_trace_line(event: AgentEvent) -> str | None:
    """从 tool 完成/失败事件提取 Plan 底栏 trace；无关工具返回 None。"""
    if event.event_type not in {"tool_completed", "tool_failed"}:
        return None

    name = event.tool_name or ""
    meta = event.metadata or {}
    args = meta.get("arguments") or {}
    if not isinstance(args, dict):
        args = {}

    ok = event.event_type == "tool_completed"

    if name == "edit_file":
        if not ok:
            return None
        path = str(args.get("path") or meta.get("path") or "")
        old_t = str(args.get("old_text") or "")
        new_t = str(args.get("new_text") or "")
        reps = int(args.get("expected_replacements") or meta.get("replacements") or 1)
        reps = max(1, reps)
        dels = _line_count(old_t) * reps
        adds = _line_count(new_t) * reps
        return f"{_basename(path)} +{adds}-{dels}"

    if name == "write_file":
        if not ok:
            return None
        path = str(args.get("path") or meta.get("path") or "")
        content = str(args.get("content") or "")
        adds = _line_count(content)
        if adds <= 0 and content:
            adds = 1
        return f"{_basename(path)} +{adds}"

    if name == "run_command":
        cmd = str(args.get("command") or "")
        extra = args.get("args") or []
        if isinstance(extra, list) and extra:
            cmd = " ".join([cmd, *[str(a) for a in extra]]).strip()
        token = (cmd.split() or ["cmd"])[0]
        label = Path(token).name if token else "cmd"
        glyph = "✅" if ok else "❌"
        return f"{glyph} {label}"

    return None
