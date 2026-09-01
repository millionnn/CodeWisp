"""GitDetector tests."""

from __future__ import annotations

from pathlib import Path

from backend.app.git.detector import GitDetector
from tests.git_helpers import init_git_repo


def test_non_git_workspace(tmp_path: Path) -> None:
    info = GitDetector.detect(tmp_path)
    assert info.is_git_repository is False
    assert info.repository_root is None


def test_git_workspace_root(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    info = GitDetector.detect(tmp_path)
    assert info.is_git_repository is True
    assert info.repository_root == str(tmp_path.resolve())


def test_git_subdirectory_detects_parent_root(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    sub = tmp_path / "projects" / "codewisp-test"
    sub.mkdir(parents=True)
    info = GitDetector.detect(sub)
    assert info.is_git_repository is True
    assert info.repository_root == str(tmp_path.resolve())
