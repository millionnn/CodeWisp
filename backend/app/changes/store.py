"""SnapshotStore：Phase 1 仅提供内存实现。"""

from __future__ import annotations

from typing import Protocol

from backend.app.changes.errors import SnapshotNotFoundError
from backend.app.changes.models import WorkspaceSnapshot


class SnapshotStore(Protocol):
    def save(self, snapshot: WorkspaceSnapshot) -> WorkspaceSnapshot:
        ...

    def get(self, snapshot_id: str) -> WorkspaceSnapshot:
        ...

    def list(
        self,
        *,
        workspace_root: str | None = None,
    ) -> list[WorkspaceSnapshot]:
        ...


class InMemorySnapshotStore:
    """进程内 Snapshot 存储（无持久化）。"""

    def __init__(self) -> None:
        self._items: dict[str, WorkspaceSnapshot] = {}

    def save(self, snapshot: WorkspaceSnapshot) -> WorkspaceSnapshot:
        self._items[snapshot.snapshot_id] = snapshot
        return snapshot

    def get(self, snapshot_id: str) -> WorkspaceSnapshot:
        try:
            return self._items[snapshot_id]
        except KeyError as exc:
            raise SnapshotNotFoundError(f"Snapshot 不存在: {snapshot_id}") from exc

    def list(
        self,
        *,
        workspace_root: str | None = None,
    ) -> list[WorkspaceSnapshot]:
        items = list(self._items.values())
        if workspace_root is not None:
            items = [s for s in items if s.workspace_root == workspace_root]
        items.sort(key=lambda s: (s.created_at or "", s.snapshot_id))
        return items

    def clear(self) -> None:
        self._items.clear()
