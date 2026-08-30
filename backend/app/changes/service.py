"""SnapshotService：capture / diff / restore（经 Workspace 安全边界）。"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable

from backend.app.changes.apply import apply_snapshot_to_workspace
from backend.app.changes.diff import compute_file_diffs, format_unified_diff
from backend.app.changes.models import (
    FileDiff,
    RestoreReport,
    SnapshotFile,
    WorkspaceSnapshot,
)
from backend.app.changes.store import InMemorySnapshotStore, SnapshotStore
from backend.app.workspace.workspace import Workspace


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

class SnapshotService:
    """Workspace Change 原语门面；不依赖 AgentLoop / SQLite。"""

    def __init__(
        self,
        workspace: Workspace,
        store: SnapshotStore | None = None,
    ) -> None:
        self._workspace = workspace
        self._store: SnapshotStore = store or InMemorySnapshotStore()

    @property
    def store(self) -> SnapshotStore:
        return self._store

    def capture(
        self,
        paths: Iterable[str],
        *,
        reason: str = "manual",
        agent_run_id: str | None = None,
        agent_step_id: str | None = None,
    ) -> WorkspaceSnapshot:
        """对显式 path 列表做文件级 snapshot（整次失败策略）。"""
        normalized = self._normalize_paths(paths)
        if not normalized:
            raise ValueError("paths 不能为空")

        files: list[SnapshotFile] = []
        for rel in normalized:
            state = self._workspace.read_text_state(rel)
            if state["exists"]:
                files.append(
                    SnapshotFile.present(state["path"], state["content"])
                )
            else:
                files.append(SnapshotFile.absent(state["path"]))

        snapshot = WorkspaceSnapshot.create(
            workspace_root=str(self._workspace.root),
            files=files,
            reason=reason,
            agent_run_id=agent_run_id,
            agent_step_id=agent_step_id,
            created_at=_utc_now_iso(),
        )
        return self._store.save(snapshot)

    def get(self, snapshot_id: str) -> WorkspaceSnapshot:
        return self._store.get(snapshot_id)

    def diff(
        self,
        before: WorkspaceSnapshot | str,
        after: WorkspaceSnapshot | str,
        *,
        include_unchanged: bool = False,
    ) -> list[FileDiff]:
        left = self._resolve_snapshot(before)
        right = self._resolve_snapshot(after)
        return compute_file_diffs(
            left, right, include_unchanged=include_unchanged
        )

    def diff_workspace(
        self,
        snapshot: WorkspaceSnapshot | str,
        *,
        include_unchanged: bool = False,
    ) -> list[FileDiff]:
        """Snapshot vs 当前工作区（仅比较 snapshot 中记录的 paths）。"""
        base = self._resolve_snapshot(snapshot)
        current_files: list[SnapshotFile] = []
        for item in base.files:
            state = self._workspace.read_text_state(item.path)
            if state["exists"]:
                current_files.append(
                    SnapshotFile.present(state["path"], state["content"])
                )
            else:
                current_files.append(SnapshotFile.absent(state["path"]))
        current = WorkspaceSnapshot.create(
            workspace_root=str(self._workspace.root),
            files=current_files,
            reason="workspace_live",
            created_at=_utc_now_iso(),
        )
        return compute_file_diffs(
            base, current, include_unchanged=include_unchanged
        )

    def format_diff(
        self,
        diffs: list[FileDiff],
        *,
        from_label: str = "a",
        to_label: str = "b",
    ) -> str:
        return format_unified_diff(
            diffs, from_label=from_label, to_label=to_label
        )

    def restore(self, snapshot: WorkspaceSnapshot | str) -> RestoreReport:
        """将 Snapshot 写回 Workspace（best-effort；非多文件事务）。"""
        target = self._resolve_snapshot(snapshot)
        return apply_snapshot_to_workspace(self._workspace, target)

    def _resolve_snapshot(
        self, snapshot: WorkspaceSnapshot | str
    ) -> WorkspaceSnapshot:
        if isinstance(snapshot, WorkspaceSnapshot):
            return snapshot
        return self._store.get(snapshot)

    def _normalize_paths(self, paths: Iterable[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for raw in paths:
            if not isinstance(raw, str) or not raw.strip():
                raise ValueError(f"非法 path: {raw!r}")
            # 先经 Workspace 规范化为 relative POSIX（顺带校验边界）
            # 不存在的文件：resolve_path 仍可解析父路径下的目标
            resolved = self._workspace.resolve_path(raw.strip())
            rel = self._workspace.relative_to_root(resolved)
            if rel in seen:
                continue
            seen.add(rel)
            ordered.append(rel)
        return ordered
