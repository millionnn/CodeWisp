"""Git domain model tests."""

from __future__ import annotations

from backend.app.git.models import (
    CommitPreview,
    GitDiff,
    GitDiffFile,
    GitFileStatus,
    GitStatus,
)


def test_git_status_counts() -> None:
    status = GitStatus(
        repository_root="/repo",
        branch="main",
        staged=[GitFileStatus(path="a.py", status="added", staged=True)],
        unstaged=[GitFileStatus(path="b.py", status="modified", unstaged=True)],
        untracked=[GitFileStatus(path="c.py", status="untracked")],
        clean=False,
    )
    assert status.staged_count == 1
    assert status.untracked_count == 1
    assert status.modified_count == 1
    assert status.clean is False


def test_git_diff_totals() -> None:
    diff = GitDiff(
        files=[
            GitDiffFile(path="a.py", change_type="modified", additions=5, deletions=2, patch=""),
            GitDiffFile(path="b.py", change_type="added", additions=10, deletions=0, patch=""),
        ]
    )
    assert diff.total_additions == 15
    assert diff.total_deletions == 2


def test_commit_preview_render() -> None:
    preview = CommitPreview(
        branch="main",
        files=["a.py"],
        additions=5,
        deletions=2,
        message="fix: bug",
    )
    text = preview.render()
    assert "Commit preview" in text
    assert "main" in text
    assert "fix: bug" in text
