"""文件级 Diff 与 unified diff 文本。"""

from __future__ import annotations

from backend.app.changes.diff import compute_file_diffs, format_unified_diff
from backend.app.changes.models import ChangeType, SnapshotFile, WorkspaceSnapshot


def _snap(files: list[SnapshotFile]) -> WorkspaceSnapshot:
    return WorkspaceSnapshot.create(workspace_root="/ws", files=files, reason="t")


def test_compute_added_modified_deleted() -> None:
    before = _snap(
        [
            SnapshotFile.present("keep.py", "same\n"),
            SnapshotFile.present("edit.py", "old\n"),
            SnapshotFile.present("gone.py", "bye\n"),
        ]
    )
    after = _snap(
        [
            SnapshotFile.present("keep.py", "same\n"),
            SnapshotFile.present("edit.py", "new\n"),
            SnapshotFile.absent("gone.py"),
            SnapshotFile.present("new.py", "hi\n"),
        ]
    )
    diffs = compute_file_diffs(before, after)
    by_path = {d.path: d for d in diffs}
    assert "keep.py" not in by_path
    assert by_path["edit.py"].change_type is ChangeType.MODIFIED
    assert by_path["gone.py"].change_type is ChangeType.DELETED
    assert by_path["new.py"].change_type is ChangeType.ADDED


def test_include_unchanged() -> None:
    before = _snap([SnapshotFile.present("a.py", "x")])
    after = _snap([SnapshotFile.present("a.py", "x")])
    diffs = compute_file_diffs(before, after, include_unchanged=True)
    assert len(diffs) == 1
    assert diffs[0].change_type is ChangeType.UNCHANGED


def test_format_unified_diff_contains_hunk() -> None:
    before = _snap([SnapshotFile.present("src/calculator.py", "return a - b\n")])
    after = _snap([SnapshotFile.present("src/calculator.py", "return a + b\n")])
    diffs = compute_file_diffs(before, after)
    text = format_unified_diff(diffs)
    assert "--- a/src/calculator.py" in text
    assert "+++ b/src/calculator.py" in text
    assert "-return a - b" in text
    assert "+return a + b" in text
