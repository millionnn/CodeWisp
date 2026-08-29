"""edit_file / write_file 工具测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry
from backend.app.workspace.workspace import Workspace


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calculator.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )
    return Workspace(tmp_path)


@pytest.fixture
def executor(workspace: Workspace) -> ToolExecutor:
    return ToolExecutor(create_default_registry(workspace=workspace))


def test_edit_file_unique_match(executor: ToolExecutor, workspace: Workspace) -> None:
    result = executor.execute(
        "edit_file",
        {
            "path": "src/calculator.py",
            "old_text": "return a + b",
            "new_text": "return a + b + 1",
            "expected_replacements": 1,
        },
    )
    assert result.success
    assert result.metadata["replacements"] == 1
    assert "return a + b + 1" in (workspace.root / "src" / "calculator.py").read_text(
        encoding="utf-8"
    )


def test_edit_file_zero_matches(executor: ToolExecutor) -> None:
    result = executor.execute(
        "edit_file",
        {
            "path": "src/calculator.py",
            "old_text": "DOES_NOT_EXIST",
            "new_text": "x",
        },
    )
    assert result.success is False
    assert "actual=0" in (result.error or "")


def test_edit_file_multiple_matches_rejected(
    executor: ToolExecutor, workspace: Workspace
) -> None:
    (workspace.root / "dup.py").write_text("AA\nAA\n", encoding="utf-8")
    result = executor.execute(
        "edit_file",
        {
            "path": "dup.py",
            "old_text": "AA",
            "new_text": "BB",
            "expected_replacements": 1,
        },
    )
    assert result.success is False
    assert "actual=2" in (result.error or "")
    assert (workspace.root / "dup.py").read_text(encoding="utf-8") == "AA\nAA\n"


def test_edit_file_expected_two(executor: ToolExecutor, workspace: Workspace) -> None:
    (workspace.root / "dup.py").write_text("AA\nAA\n", encoding="utf-8")
    result = executor.execute(
        "edit_file",
        {
            "path": "dup.py",
            "old_text": "AA",
            "new_text": "BB",
            "expected_replacements": 2,
        },
    )
    assert result.success
    assert result.output["replacements"] == 2
    assert (workspace.root / "dup.py").read_text(encoding="utf-8") == "BB\nBB\n"


def test_edit_file_empty_old_text(executor: ToolExecutor) -> None:
    result = executor.execute(
        "edit_file",
        {"path": "src/calculator.py", "old_text": "", "new_text": "x"},
    )
    assert result.success is False
    assert "old_text" in (result.error or "")


def test_edit_then_read_verifies_change(executor: ToolExecutor) -> None:
    edit = executor.execute(
        "edit_file",
        {
            "path": "src/calculator.py",
            "old_text": "return a + b",
            "new_text": "return a * b",
        },
    )
    assert edit.success
    read = executor.execute("read_file", {"path": "src/calculator.py"})
    assert read.success
    assert "return a * b" in read.output["content"]


def test_write_file_create(executor: ToolExecutor, workspace: Workspace) -> None:
    result = executor.execute(
        "write_file",
        {"path": "src/utils.py", "content": "def helper():\n    return 1\n"},
    )
    assert result.success
    assert result.metadata["created"] is True
    assert result.metadata["overwritten"] is False
    assert (workspace.root / "src" / "utils.py").is_file()


def test_write_file_no_overwrite(executor: ToolExecutor) -> None:
    result = executor.execute(
        "write_file",
        {"path": "src/calculator.py", "content": "stolen\n", "overwrite": False},
    )
    assert result.success is False
    assert "overwrite" in (result.error or "").lower()


def test_write_file_overwrite(executor: ToolExecutor, workspace: Workspace) -> None:
    result = executor.execute(
        "write_file",
        {"path": "src/calculator.py", "content": "NEW\n", "overwrite": True},
    )
    assert result.success
    assert result.metadata["overwritten"] is True
    assert (workspace.root / "src" / "calculator.py").read_text(encoding="utf-8") == "NEW\n"


def test_write_file_empty_and_unicode(executor: ToolExecutor, workspace: Workspace) -> None:
    empty = executor.execute("write_file", {"path": "blank.txt", "content": ""})
    assert empty.success
    assert (workspace.root / "blank.txt").read_text(encoding="utf-8") == ""

    uni = executor.execute("write_file", {"path": "你好.py", "content": "# 中文\n"})
    assert uni.success
    assert (workspace.root / "你好.py").read_text(encoding="utf-8") == "# 中文\n"


def test_write_file_nested_parents(executor: ToolExecutor, workspace: Workspace) -> None:
    result = executor.execute(
        "write_file",
        {"path": "deep/nested/new.py", "content": "pass\n"},
    )
    assert result.success
    assert (workspace.root / "deep" / "nested" / "new.py").is_file()


def test_write_file_path_boundary(executor: ToolExecutor) -> None:
    for bad in ("../outside.txt", "../../outside.txt", "/tmp/outside.txt"):
        result = executor.execute(
            "write_file",
            {"path": bad, "content": "x"},
        )
        assert result.success is False, bad


def test_edit_file_path_boundary(executor: ToolExecutor) -> None:
    result = executor.execute(
        "edit_file",
        {"path": "../outside.txt", "old_text": "a", "new_text": "b"},
    )
    assert result.success is False


def test_registry_exposes_write_tools(workspace: Workspace) -> None:
    names = {t.name for t in create_default_registry(workspace=workspace).list_tools()}
    assert {"edit_file", "write_file", "read_file", "list_files"} <= names
