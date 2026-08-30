"""InMemorySnapshotStore。"""

from __future__ import annotations

import pytest

from backend.app.changes.errors import SnapshotNotFoundError
from backend.app.changes.models import SnapshotFile, WorkspaceSnapshot
from backend.app.changes.store import InMemorySnapshotStore


def test_store_save_get_list() -> None:
    store = InMemorySnapshotStore()
    snap = WorkspaceSnapshot.create(
        workspace_root="/ws-a",
        files=[SnapshotFile.present("a.py", "1")],
        reason="t",
        created_at="2026-01-01T00:00:00+00:00",
    )
    store.save(snap)
    assert store.get(snap.snapshot_id).files[0].content == "1"
    assert len(store.list(workspace_root="/ws-a")) == 1
    assert store.list(workspace_root="/other") == []


def test_store_missing() -> None:
    store = InMemorySnapshotStore()
    with pytest.raises(SnapshotNotFoundError):
        store.get("snap_missing")
