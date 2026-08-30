"""SnapshotService：capture / diff / restore + 安全边界。"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.changes.errors import RestoreError
from backend.app.changes.models import ChangeType
from backend.app.changes.service import SnapshotService
from backend.app.changes.store import InMemorySnapshotStore
from backend.app.workspace.errors import PathOutsideWorkspaceError
from backend.app.workspace.workspace import Workspace


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calculator.py").write_text(
        "def add(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    return Workspace(tmp_path)


@pytest.fixture
def service(ws: Workspace) -> SnapshotService:
    return SnapshotService(ws, InMemorySnapshotStore())


def test_capture_and_diff_workspace(service: SnapshotService, ws: Workspace) -> None:
    before = service.capture(["src/calculator.py", "src/new.py"], reason="before")
    assert before.file_map()["src/calculator.py"].exists is True
    assert before.file_map()["src/new.py"].exists is False

    ws.write_text("src/calculator.py", "def add(a, b):\n    return a + b\n", overwrite=True)
    ws.write_text("src/new.py", "print(1)\n")

    diffs = service.diff_workspace(before)
    by_path = {d.path: d for d in diffs}
    assert by_path["src/calculator.py"].change_type is ChangeType.MODIFIED
    assert by_path["src/new.py"].change_type is ChangeType.ADDED
    text = service.format_diff(diffs)
    assert "return a + b" in text


def test_restore_modified_created_deleted(service: SnapshotService, ws: Workspace) -> None:
    snap = service.capture(
        ["src/calculator.py", "src/created.py", "src/to_delete.py"],
        reason="baseline",
    )
    # 基准：created 不存在；to_delete 先创建再在 snapshot 后删掉以测「恢复存在」
    ws.write_text("src/to_delete.py", "keep-me\n")
    snap2 = service.capture(
        ["src/calculator.py", "src/created.py", "src/to_delete.py"],
        reason="with-delete-target",
    )

    ws.write_text("src/calculator.py", "CHANGED\n", overwrite=True)
    ws.write_text("src/created.py", "NEW\n")
    ws.delete_file("src/to_delete.py")

    report = service.restore(snap2)
    assert report.ok
    assert (ws.root / "src" / "calculator.py").read_text(encoding="utf-8") == (
        "def add(a, b):\n    return a - b\n"
    )
    assert not (ws.root / "src" / "created.py").exists()
    assert (ws.root / "src" / "to_delete.py").read_text(encoding="utf-8") == "keep-me\n"
    # 历史 snapshot 仍在 store
    assert service.get(snap.snapshot_id).snapshot_id == snap.snapshot_id


def test_diff_two_snapshots(service: SnapshotService, ws: Workspace) -> None:
    a = service.capture(["src/calculator.py"])
    ws.write_text("src/calculator.py", "X\n", overwrite=True)
    b = service.capture(["src/calculator.py"])
    diffs = service.diff(a, b)
    assert len(diffs) == 1
    assert diffs[0].change_type is ChangeType.MODIFIED


def test_capture_path_traversal(service: SnapshotService) -> None:
    with pytest.raises(PathOutsideWorkspaceError):
        service.capture(["../outside.txt"])


def test_restore_rejects_foreign_workspace(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    ws_a = Workspace(tmp_path / "a")
    ws_b = Workspace(tmp_path / "b")
    (tmp_path / "a" / "f.txt").write_text("a\n", encoding="utf-8")

    store = InMemorySnapshotStore()
    svc_a = SnapshotService(ws_a, store)
    snap = svc_a.capture(["f.txt"])

    svc_b = SnapshotService(ws_b, store)
    with pytest.raises(RestoreError, match="不一致"):
        svc_b.restore(snap)


def test_unicode_path_round_trip(service: SnapshotService, ws: Workspace) -> None:
    ws.write_text("你好/文件.txt", "中文\n")
    snap = service.capture(["你好/文件.txt"])
    ws.write_text("你好/文件.txt", "改\n", overwrite=True)
    service.restore(snap)
    assert (ws.root / "你好" / "文件.txt").read_text(encoding="utf-8") == "中文\n"
