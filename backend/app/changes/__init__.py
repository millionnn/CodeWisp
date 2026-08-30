"""Workspace Change Management（V0.9）。

Phase 1：Snapshot / Diff / Restore 原语。
Phase 2：AgentStep 关联 + SQLite 持久化 + WriteChangeTracker。
Phase 3：Revert step/run + Permission + 审计 Snapshot。
"""

from backend.app.changes.apply import apply_snapshot_to_workspace
from backend.app.changes.diff import compute_file_diffs, format_unified_diff
from backend.app.changes.errors import (
    ChangeError,
    RestoreError,
    RevertDeniedError,
    RevertError,
    SnapshotNotFoundError,
)
from backend.app.changes.ids import new_file_change_id, new_snapshot_id
from backend.app.changes.models import (
    ChangeType,
    FileChangeRecord,
    FileDiff,
    RestoreReport,
    RevertReport,
    SnapshotFile,
    WorkspaceSnapshot,
)
from backend.app.changes.revert import RevertService
from backend.app.changes.service import SnapshotService
from backend.app.changes.store import InMemorySnapshotStore, SnapshotStore
from backend.app.changes.tracker import WRITE_TOOLS, WriteChangeTracker

__all__ = [
    "WRITE_TOOLS",
    "ChangeError",
    "ChangeType",
    "FileChangeRecord",
    "FileDiff",
    "InMemorySnapshotStore",
    "RestoreError",
    "RestoreReport",
    "RevertDeniedError",
    "RevertError",
    "RevertReport",
    "RevertService",
    "SnapshotFile",
    "SnapshotNotFoundError",
    "SnapshotService",
    "SnapshotStore",
    "WriteChangeTracker",
    "WorkspaceSnapshot",
    "apply_snapshot_to_workspace",
    "compute_file_diffs",
    "format_unified_diff",
    "new_file_change_id",
    "new_snapshot_id",
]
