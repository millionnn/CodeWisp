"""只读 Coding Tools 测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.tools.builtin.workspace import (
    GlobTool,
    ListFilesTool,
    ReadFileTool,
    SearchCodeTool,
)
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry
from backend.app.workspace.workspace import Workspace


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "main.py").write_text("print('hi')\nANSWER = 42\n", encoding="utf-8")
    (tmp_path / "pkg" / "data.bin").write_bytes(b"\x00\x00")
    return Workspace(tmp_path)


@pytest.fixture
def executor(workspace: Workspace) -> ToolExecutor:
    return ToolExecutor(create_default_registry(workspace=workspace))


def test_list_files_tool(executor: ToolExecutor) -> None:
    result = executor.execute("list_files", {"path": ".", "max_depth": 2})
    assert result.success
    assert result.output["count"] >= 1
    paths = [e["path"] for e in result.output["entries"]]
    assert "pkg/main.py" in paths


def test_glob_tool(executor: ToolExecutor) -> None:
    result = executor.execute("glob", {"pattern": "**/*.py"})
    assert result.success
    assert "pkg/main.py" in result.output["matches"]


def test_read_file_tool(executor: ToolExecutor) -> None:
    result = executor.execute("read_file", {"path": "pkg/main.py", "start_line": 2, "end_line": 2})
    assert result.success
    assert "ANSWER = 42" in result.output["content"]
    assert result.output["start_line"] == 2


def test_read_file_binary_failure(executor: ToolExecutor) -> None:
    result = executor.execute("read_file", {"path": "pkg/data.bin"})
    assert result.success is False
    assert "二进制" in (result.error or "")


def test_search_code_tool(executor: ToolExecutor) -> None:
    result = executor.execute("search_code", {"query": "ANSWER"})
    assert result.success
    assert result.output["hits"][0]["line"] == 2


def test_search_empty_query(executor: ToolExecutor) -> None:
    result = executor.execute("search_code", {"query": ""})
    # schema 允许空字符串，工具内部失败
    assert result.success is False


def test_path_traversal_via_tool(executor: ToolExecutor) -> None:
    result = executor.execute("read_file", {"path": "../outside.py"})
    assert result.success is False
    assert "workspace" in (result.error or "").lower() or "边界" in (result.error or "")


def test_registry_exposes_coding_schemas(workspace: Workspace) -> None:
    names = {t.name for t in create_default_registry(workspace=workspace).list_tools()}
    assert {
        "list_files",
        "glob",
        "read_file",
        "search_code",
        "edit_file",
        "write_file",
        "run_command",
        "calculator",
        "get_current_time",
    } <= names


def test_tools_use_injected_workspace(tmp_path: Path) -> None:
    tool = ListFilesTool(Workspace(tmp_path))
    (tmp_path / "only_here.txt").write_text("x", encoding="utf-8")
    result = tool.execute({"path": "."})
    assert result.success
    assert any(e["path"] == "only_here.txt" for e in result.output["entries"])
