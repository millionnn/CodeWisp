"""Git tool tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.handler import AlwaysDenyPermissionHandler, ScriptedPermissionHandler
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry
from backend.app.workspace.workspace import Workspace
from tests.git_helpers import git_commit_all, init_git_repo


@pytest.fixture
def git_executor(tmp_path: Path) -> ToolExecutor:
    init_git_repo(tmp_path)
    ws = Workspace(tmp_path)
    return ToolExecutor(create_default_registry(workspace=ws))


def test_git_status_tool(git_executor: ToolExecutor) -> None:
    result = git_executor.execute("git_status", {})
    assert result.success
    assert result.output["clean"] is True


def test_git_diff_tool(git_executor: ToolExecutor, tmp_path: Path) -> None:
    (tmp_path / "f.py").write_text("a\n", encoding="utf-8")
    git_commit_all(tmp_path, "add f")
    (tmp_path / "f.py").write_text("b\n", encoding="utf-8")
    result = git_executor.execute("git_diff", {})
    assert result.success
    assert result.metadata.get("file_count", 0) >= 1


def test_git_log_tool(git_executor: ToolExecutor) -> None:
    result = git_executor.execute("git_log", {"limit": 5})
    assert result.success
    assert result.output["count"] >= 1


def test_git_branch_list(git_executor: ToolExecutor) -> None:
    result = git_executor.execute("git_branch", {"action": "list"})
    assert result.success
    assert "branches" in result.output


def test_git_commit_ask_without_handler(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    (tmp_path / "x.py").write_text("1\n", encoding="utf-8")
    ws = Workspace(tmp_path)
    registry = create_default_registry(workspace=ws, permission_handler=None)
    executor = ToolExecutor(registry)
    result = executor.execute("git_commit", {"message": "test commit"})
    assert result.metadata.get("permission_required") is True


def test_git_commit_deny(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    (tmp_path / "x.py").write_text("1\n", encoding="utf-8")
    ws = Workspace(tmp_path)
    registry = create_default_registry(
        workspace=ws,
        permission_handler=AlwaysDenyPermissionHandler(),
    )
    executor = ToolExecutor(registry)
    result = executor.execute("git_commit", {"message": "test commit"})
    assert result.success is False
    assert result.output.get("user_denied") is True


def test_git_commit_allow(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    (tmp_path / "x.py").write_text("1\n", encoding="utf-8")
    ws = Workspace(tmp_path)
    registry = create_default_registry(
        workspace=ws,
        permission_handler=ScriptedPermissionHandler([PermissionDecision.ALLOW]),
    )
    executor = ToolExecutor(registry)
    result = executor.execute("git_commit", {"message": "test commit"})
    assert result.success
    assert result.output.get("commit_id")


def test_non_git_status(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    executor = ToolExecutor(create_default_registry(workspace=ws))
    result = executor.execute("git_status", {})
    assert result.success
    assert result.metadata.get("is_git_repository") is False


def test_registry_includes_git_tools(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    names = {
        t["function"]["name"]
        for t in create_default_registry(workspace=Workspace(tmp_path)).list_schemas()
    }
    assert {
        "git_status",
        "git_diff",
        "git_log",
        "git_branch",
        "git_commit",
    }.issubset(names)
