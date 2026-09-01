"""GitRepository low-level tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.git.errors import GitOperationError
from backend.app.git.repository import GitRepository
from tests.git_helpers import git_commit_all, init_git_repo


@pytest.fixture
def repo_root(tmp_path: Path) -> Path:
    init_git_repo(tmp_path)
    return tmp_path


def test_status_clean(repo_root: Path) -> None:
    repo = GitRepository(repo_root)
    status = repo.status()
    assert status.clean is True
    assert status.branch == "main" or status.branch is not None


def test_status_modified_and_untracked(repo_root: Path) -> None:
    (repo_root / "modified.py").write_text("x\n", encoding="utf-8")
    (repo_root / "new.py").write_text("y\n", encoding="utf-8")
    git_commit_all(repo_root, "add modified")
    (repo_root / "modified.py").write_text("changed\n", encoding="utf-8")
    (repo_root / "untracked.py").write_text("z\n", encoding="utf-8")

    status = GitRepository(repo_root).status()
    assert status.clean is False
    assert status.untracked_count >= 1


def test_diff_working_tree(repo_root: Path) -> None:
    (repo_root / "file.py").write_text("old\n", encoding="utf-8")
    git_commit_all(repo_root, "add file")
    (repo_root / "file.py").write_text("new\n", encoding="utf-8")

    diff = GitRepository(repo_root).diff()
    assert diff.total_additions >= 1 or diff.total_deletions >= 1
    assert any(f.path == "file.py" for f in diff.files)


def test_log_limit(repo_root: Path) -> None:
    for i in range(3):
        (repo_root / f"f{i}.txt").write_text(f"{i}\n", encoding="utf-8")
        git_commit_all(repo_root, f"commit {i}")

    commits = GitRepository(repo_root).log(limit=2)
    assert len(commits) == 2


def test_branch_list(repo_root: Path) -> None:
    repo = GitRepository(repo_root)
    branches = repo.list_branches()
    assert any(b.current for b in branches)


def test_shell_false_no_injection(repo_root: Path) -> None:
    repo = GitRepository(repo_root)
    result = repo.run("status")
    assert result.exit_code == 0


def test_commit_message_with_special_chars(repo_root: Path) -> None:
    (repo_root / "x.py").write_text("1\n", encoding="utf-8")
    repo = GitRepository(repo_root)
    repo.add(["x.py"])
    commit_id = repo.commit('fix: test; echo "injection"')
    assert len(commit_id) >= 5
