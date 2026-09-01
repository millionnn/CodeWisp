"""GitService tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.git.errors import GitNotRepositoryError
from backend.app.git.models import GitRepositoryInfo
from backend.app.git.service import GitService
from backend.app.workspace.workspace import Workspace
from tests.git_helpers import git_commit_all, init_git_repo


@pytest.fixture
def git_workspace(tmp_path: Path) -> Workspace:
    init_git_repo(tmp_path)
    return Workspace(tmp_path)


def test_non_git_status(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    result = GitService(ws).status()
    assert isinstance(result, GitRepositoryInfo)
    assert result.is_git_repository is False


def test_git_status(git_workspace: Workspace) -> None:
    status = GitService(git_workspace).status()
    assert status.clean is True


def test_git_diff(git_workspace: Workspace) -> None:
    root = git_workspace.root
    (root / "calc.py").write_text("def add(a,b): return a+b\n", encoding="utf-8")
    git_commit_all(root, "add calc")
    (root / "calc.py").write_text("def add(a,b): return a-b\n", encoding="utf-8")

    diff = GitService(git_workspace).diff()
    assert diff.total_additions + diff.total_deletions > 0


def test_git_log(git_workspace: Workspace) -> None:
    commits = GitService(git_workspace).log(limit=5)
    assert len(commits) >= 1


def test_git_commit(git_workspace: Workspace) -> None:
    root = git_workspace.root
    (root / "new.py").write_text("x\n", encoding="utf-8")
    result = GitService(git_workspace).commit("feat: add new.py", paths=["new.py"])
    assert result["commit_id"]
    status = GitService(git_workspace).status()
    assert status.clean is True


def test_workspace_isolation(tmp_path: Path) -> None:
    repo_a = tmp_path / "a"
    repo_b = tmp_path / "b"
    repo_a.mkdir()
    repo_b.mkdir()
    init_git_repo(repo_a)
    init_git_repo(repo_b)

    ws_a = Workspace(repo_a)
    ws_b = Workspace(repo_b)

    (repo_a / "secret.py").write_text("a\n", encoding="utf-8")
    git_commit_all(repo_a, "a secret")

    with pytest.raises(Exception):  # noqa: B017
        GitService(ws_b).diff(path="../a/secret.py")
