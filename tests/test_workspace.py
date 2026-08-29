"""Workspace 单元测试（全部使用 tmp_path，不改真实仓库）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.workspace.errors import PathOutsideWorkspaceError, WorkspaceIOError
from backend.app.workspace.workspace import Workspace


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calculator.py").write_text("def add(a, b):\n    return a + b\n", encoding="utf-8")
    (tmp_path / "src" / "util.py").write_text("VALUE = 1\n", encoding="utf-8")
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "test_calc.py").write_text("from src.calculator import add\n", encoding="utf-8")
    (tmp_path / "empty").mkdir()
    (tmp_path / "README.md").write_text("# Demo\n", encoding="utf-8")
    return Workspace(tmp_path)


def test_root(ws: Workspace, tmp_path: Path) -> None:
    assert ws.root == tmp_path.resolve()


def test_nested_path(ws: Workspace) -> None:
    resolved = ws.resolve_path("src/calculator.py")
    assert resolved.name == "calculator.py"
    assert resolved.is_file()


def test_nonexistent_resolve_still_inside(ws: Workspace) -> None:
    # resolve 允许尚不存在的路径，只要落在边界内
    p = ws.resolve_path("missing.txt")
    assert not p.exists()
    assert str(ws.root) in str(p)


def test_path_traversal_rejected(ws: Workspace) -> None:
    with pytest.raises(PathOutsideWorkspaceError):
        ws.resolve_path("../outside.txt")
    with pytest.raises(PathOutsideWorkspaceError):
        ws.resolve_path("src/../../outside.txt")


def test_absolute_outside_rejected(ws: Workspace, tmp_path: Path) -> None:
    outside = tmp_path.parent / "not_ws.txt"
    outside.write_text("x", encoding="utf-8")
    with pytest.raises(PathOutsideWorkspaceError):
        ws.resolve_path(str(outside))


def test_list_root(ws: Workspace) -> None:
    entries = ws.list(".", max_depth=1)
    paths = {e["path"] for e in entries}
    assert "src" in paths
    assert "tests" in paths
    assert "README.md" in paths
    assert "src/calculator.py" not in paths  # depth=1


def test_list_nested(ws: Workspace) -> None:
    entries = ws.list("src", max_depth=1)
    paths = {e["path"] for e in entries}
    assert "src/calculator.py" in paths
    assert all(e["type"] in {"file", "directory"} for e in entries)


def test_list_empty_directory(ws: Workspace) -> None:
    assert ws.list("empty") == []


def test_list_nonexistent(ws: Workspace) -> None:
    with pytest.raises(WorkspaceIOError, match="不存在"):
        ws.list("nope")


def test_glob_py(ws: Workspace) -> None:
    matches = ws.glob("*.py")
    assert matches == []  # root 无 py
    matches = ws.glob("**/*.py")
    assert "src/calculator.py" in matches
    assert "tests/test_calc.py" in matches


def test_glob_specific(ws: Workspace) -> None:
    matches = ws.glob("test_*.py", path="tests")
    assert matches == ["tests/test_calc.py"]


def test_glob_no_match(ws: Workspace) -> None:
    assert ws.glob("**/*.rs") == []


def test_read_utf8(ws: Workspace) -> None:
    data = ws.read("src/calculator.py")
    assert "def add" in data["content"]
    assert data["path"] == "src/calculator.py"
    assert data["start_line"] == 1
    assert data["total_lines"] == 2


def test_read_line_range(ws: Workspace) -> None:
    data = ws.read("src/calculator.py", start_line=2, end_line=2)
    assert data["content"].strip() == "return a + b"
    assert data["start_line"] == 2
    assert data["end_line"] == 2


def test_read_nonexistent(ws: Workspace) -> None:
    with pytest.raises(WorkspaceIOError, match="不存在"):
        ws.read("missing.py")


def test_read_binary(ws: Workspace, tmp_path: Path) -> None:
    (tmp_path / "blob.bin").write_bytes(b"\x00\x01\x02\xff")
    with pytest.raises(WorkspaceIOError, match="二进制"):
        ws.read("blob.bin")


def test_read_oversized(ws: Workspace, tmp_path: Path) -> None:
    (tmp_path / "big.txt").write_text("x" * 1000, encoding="utf-8")
    with pytest.raises(WorkspaceIOError, match="过大"):
        ws.read("big.txt", max_bytes=100)


def test_read_path_traversal(ws: Workspace) -> None:
    with pytest.raises(PathOutsideWorkspaceError):
        ws.read("../secret.txt")


def test_search_single_and_line(ws: Workspace) -> None:
    hits = ws.search("return a + b")
    assert len(hits) == 1
    assert hits[0]["file"] == "src/calculator.py"
    assert hits[0]["line"] == 2


def test_search_multiple_files(ws: Workspace) -> None:
    hits = ws.search("calculator")
    files = {h["file"] for h in hits}
    assert "tests/test_calc.py" in files


def test_search_no_match(ws: Workspace) -> None:
    assert ws.search("zzz_not_found") == []


def test_search_empty_query(ws: Workspace) -> None:
    with pytest.raises(WorkspaceIOError, match="不能为空"):
        ws.search("")


def test_search_skips_binary(ws: Workspace, tmp_path: Path) -> None:
    (tmp_path / "a.bin").write_bytes(b"secret\x00payload")
    assert ws.search("secret") == []


def test_search_path_traversal(ws: Workspace) -> None:
    with pytest.raises(PathOutsideWorkspaceError):
        ws.search("x", path="../")
