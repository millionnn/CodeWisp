"""Workspace 写入 / 确定性替换测试（tmp_path）。"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.workspace.errors import PathOutsideWorkspaceError, WorkspaceIOError
from backend.app.workspace.workspace import Workspace


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calculator.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    return Workspace(tmp_path)


def test_write_create_new(ws: Workspace) -> None:
    result = ws.write_text("src/utils.py", "X = 1\n")
    assert result["created"] is True
    assert result["overwritten"] is False
    assert (ws.root / "src" / "utils.py").read_text(encoding="utf-8") == "X = 1\n"


def test_write_exists_no_overwrite(ws: Workspace) -> None:
    with pytest.raises(WorkspaceIOError, match="overwrite=false"):
        ws.write_text("src/calculator.py", "hacked\n", overwrite=False)
    assert "def add" in (ws.root / "src" / "calculator.py").read_text(encoding="utf-8")


def test_write_overwrite(ws: Workspace) -> None:
    result = ws.write_text("src/calculator.py", "OK\n", overwrite=True)
    assert result["created"] is False
    assert result["overwritten"] is True
    assert (ws.root / "src" / "calculator.py").read_text(encoding="utf-8") == "OK\n"


def test_write_empty_file(ws: Workspace) -> None:
    result = ws.write_text("empty.txt", "")
    assert result["created"] is True
    assert result["bytes_written"] == 0
    assert (ws.root / "empty.txt").read_text(encoding="utf-8") == ""


def test_write_unicode(ws: Workspace) -> None:
    ws.write_text("你好.txt", "中文内容✓\n")
    assert (ws.root / "你好.txt").read_text(encoding="utf-8") == "中文内容✓\n"


def test_write_nested_creates_parents(ws: Workspace) -> None:
    result = ws.write_text("pkg/a/b/mod.py", "pass\n")
    assert result["created"] is True
    assert (ws.root / "pkg" / "a" / "b" / "mod.py").is_file()


def test_write_path_traversal(ws: Workspace) -> None:
    with pytest.raises(PathOutsideWorkspaceError):
        ws.write_text("../outside.txt", "nope")
    with pytest.raises(PathOutsideWorkspaceError):
        ws.write_text("../../outside.txt", "nope")


def test_write_absolute_outside(ws: Workspace, tmp_path: Path) -> None:
    outside = tmp_path.parent / "outside_write.txt"
    with pytest.raises(PathOutsideWorkspaceError):
        ws.write_text(str(outside), "nope")
    assert not outside.exists()


def test_write_symlink_escape(ws: Workspace, tmp_path: Path) -> None:
    outside_dir = tmp_path.parent / "outside_dir_write"
    outside_dir.mkdir(exist_ok=True)
    link = tmp_path / "escape"
    try:
        link.symlink_to(outside_dir)
    except OSError:
        pytest.skip("无法创建 symlink")
    with pytest.raises(PathOutsideWorkspaceError):
        ws.write_text("escape/leaked.txt", "secret")
    assert not (outside_dir / "leaked.txt").exists()


def test_replace_unique(ws: Workspace) -> None:
    result = ws.replace_text(
        "src/calculator.py",
        "return a + b",
        "return a + b + 1",
        expected_replacements=1,
    )
    assert result["replacements"] == 1
    text = (ws.root / "src" / "calculator.py").read_text(encoding="utf-8")
    assert "return a + b + 1" in text
    assert "return a + b\n" not in text


def test_replace_zero_matches(ws: Workspace) -> None:
    original = (ws.root / "src" / "calculator.py").read_text(encoding="utf-8")
    with pytest.raises(WorkspaceIOError, match="actual=0"):
        ws.replace_text("src/calculator.py", "no_such_token", "x", expected_replacements=1)
    assert (ws.root / "src" / "calculator.py").read_text(encoding="utf-8") == original


def test_replace_too_many_matches(ws: Workspace, tmp_path: Path) -> None:
    (tmp_path / "dup.py").write_text("FOO = 1\nFOO = 2\n", encoding="utf-8")
    with pytest.raises(WorkspaceIOError, match="actual=2"):
        ws.replace_text("dup.py", "FOO", "BAR", expected_replacements=1)
    assert (tmp_path / "dup.py").read_text(encoding="utf-8") == "FOO = 1\nFOO = 2\n"


def test_replace_expected_two(ws: Workspace, tmp_path: Path) -> None:
    (tmp_path / "dup.py").write_text("FOO = 1\nFOO = 2\n", encoding="utf-8")
    result = ws.replace_text("dup.py", "FOO", "BAR", expected_replacements=2)
    assert result["replacements"] == 2
    assert (tmp_path / "dup.py").read_text(encoding="utf-8") == "BAR = 1\nBAR = 2\n"


def test_replace_empty_old_text(ws: Workspace) -> None:
    with pytest.raises(WorkspaceIOError, match="old_text 不能为空"):
        ws.replace_text("src/calculator.py", "", "x")


def test_replace_path_traversal(ws: Workspace) -> None:
    with pytest.raises(PathOutsideWorkspaceError):
        ws.replace_text("../outside.txt", "a", "b")


def test_replace_then_read_verifies(ws: Workspace) -> None:
    ws.replace_text(
        "src/calculator.py",
        "return a + b",
        "return a * b",
        expected_replacements=1,
    )
    data = ws.read("src/calculator.py")
    assert "return a * b" in data["content"]
