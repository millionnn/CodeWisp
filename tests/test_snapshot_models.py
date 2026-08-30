"""Snapshot / Diff 领域模型测试。"""

from __future__ import annotations

import pytest

from backend.app.changes.models import (
    ChangeType,
    SnapshotFile,
    WorkspaceSnapshot,
    content_sha256,
)


def test_snapshot_file_present_and_absent() -> None:
    present = SnapshotFile.present("src/a.py", "x = 1\n")
    assert present.exists is True
    assert present.size == len("x = 1\n".encode("utf-8"))
    assert present.content_hash == content_sha256("x = 1\n")

    absent = SnapshotFile.absent("src/b.py")
    assert absent.exists is False
    assert absent.content is None
    assert absent.size is None


def test_snapshot_file_rejects_bad_path() -> None:
    with pytest.raises(ValueError):
        SnapshotFile.present("/abs.py", "x")
    with pytest.raises(ValueError):
        SnapshotFile.present("../escape.py", "x")
    with pytest.raises(ValueError):
        SnapshotFile.absent("src/../x.py")


def test_snapshot_file_absent_rejects_content() -> None:
    with pytest.raises(ValueError):
        SnapshotFile(path="a.py", exists=False, content="")


def test_workspace_snapshot_round_trip() -> None:
    snap = WorkspaceSnapshot.create(
        workspace_root="/tmp/ws",
        files=[
            SnapshotFile.present("a.py", "A"),
            SnapshotFile.absent("b.py"),
        ],
        reason="test",
        agent_run_id="run_1",
        agent_step_id="step_1",
        created_at="2026-01-01T00:00:00+00:00",
    )
    restored = WorkspaceSnapshot.from_dict(snap.to_dict())
    assert restored.snapshot_id == snap.snapshot_id
    assert restored.agent_run_id == "run_1"
    assert restored.file_map()["a.py"].content == "A"
    assert restored.file_map()["b.py"].exists is False
    assert ChangeType.ADDED.value == "ADDED"
