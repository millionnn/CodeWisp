"""运行时写工具变更追踪（经 AgentEvent；不访问 SQLite）。"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.agent.events import AgentEvent
from backend.app.changes.diff import compute_file_diffs
from backend.app.changes.models import ChangeType, SnapshotFile
from backend.app.workspace.errors import WorkspaceError
from backend.app.workspace.workspace import Workspace

WRITE_TOOLS = frozenset({"edit_file", "write_file"})

#Agent 调用 edit_file/write_file 时，悄悄记下改前/改后内容

@dataclass
class TrackedWrite:
    """单次写工具调用的 before/after 文件状态（内存）。"""

    step_index: int
    tool_call_id: str
    tool_name: str
    path: str
    before: SnapshotFile
    after: SnapshotFile | None = None


class WriteChangeTracker:
    """监听 tool_called / tool_completed，在写发生前后捕获文件状态。

    AgentLoop / Tools 不依赖本类；由 AgentService 经 CompositeEventSink 挂载。
    """

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace
        self._queues: dict[int, list[TrackedWrite]] = {}
        self._completed: list[TrackedWrite] = []

    @property
    def completed(self) -> list[TrackedWrite]:
        return list(self._completed)

    def emit(self, event: AgentEvent) -> None:
        name = (event.tool_name or "").strip()
        if name not in WRITE_TOOLS:
            return

        if event.event_type == "tool_called":
            self._on_called(event, name)
        elif event.event_type in {"tool_completed", "tool_failed"}:
            self._on_finished(event)

    def _on_called(self, event: AgentEvent, tool_name: str) -> None:
        meta = event.metadata or {}
        args = meta.get("arguments") or {}
        if not isinstance(args, dict):
            return
        raw_path = args.get("path")
        if not isinstance(raw_path, str) or not raw_path.strip():
            return
        call_id = str(meta.get("tool_call_id") or "").strip() or f"call_step{event.step}"
        try:
            before = self._read_file(raw_path.strip())
        except WorkspaceError:
            return
        tracked = TrackedWrite(
            step_index=event.step,
            tool_call_id=call_id,
            tool_name=tool_name,
            path=before.path,
            before=before,
        )
        self._queues.setdefault(event.step, []).append(tracked)

    def _on_finished(self, event: AgentEvent) -> None:
        queue = self._queues.get(event.step) or []
        if not queue:
            return
        tracked = queue.pop(0)
        meta = event.metadata or {}
        # ToolResult.metadata / output 可能带规范化 path
        path = tracked.path
        out = meta.get("output")
        if isinstance(out, dict) and isinstance(out.get("path"), str):
            path = out["path"]
        elif isinstance(meta.get("path"), str):
            path = meta["path"]
        try:
            after = self._read_file(path)
        except WorkspaceError:
            after = tracked.before
        tracked.path = after.path
        tracked.after = after
        self._completed.append(tracked)

    def _read_file(self, path: str) -> SnapshotFile:
        state = self._workspace.read_text_state(path)
        if state["exists"]:
            return SnapshotFile.present(state["path"], state["content"])
        return SnapshotFile.absent(state["path"])

    def change_type_for(self, tracked: TrackedWrite) -> ChangeType:
        after = tracked.after or tracked.before
        diffs = compute_file_diffs(
            {tracked.path: tracked.before},
            {tracked.path: after},
            include_unchanged=True,
        )
        return diffs[0].change_type if diffs else ChangeType.UNCHANGED
