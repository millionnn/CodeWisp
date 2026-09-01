"""GitContextProvider tests."""

from __future__ import annotations

from pathlib import Path

from backend.app.context.budget import ContextBudget
from backend.app.git.context import GitContextProvider
from tests.git_helpers import git_commit_all, init_git_repo


def test_git_context_in_assembly(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    (tmp_path / "app.py").write_text("x=1\n", encoding="utf-8")
    git_commit_all(tmp_path, "add app")
    (tmp_path / "app.py").write_text("x=2\n", encoding="utf-8")

    provider = GitContextProvider(str(tmp_path.resolve()))
    text = provider.build_workspace_context()
    assert "## Git" in text
    assert "Git repository: yes" in text
    assert "Branch:" in text
    assert "Changed files:" in text
    assert "Recent commits:" in text
    assert "@@" not in text  # no full diff


def test_non_git_context(tmp_path: Path) -> None:
    text = GitContextProvider(str(tmp_path)).build_workspace_context()
    assert "not a git repository" in text


def test_context_manager_includes_git(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    from backend.app.context.manager import DefaultContextManager

    cm = DefaultContextManager(
        session_id="sess_test",
        workspace_root=str(tmp_path.resolve()),
        budget=ContextBudget.from_context_window(32_000),
        persist=False,
        git_context_provider=GitContextProvider(str(tmp_path.resolve())),
    )
    cm.begin_run("test task")
    from backend.app.llm.messages import Conversation

    conv = Conversation()
    conv.add_system("system")
    parts = cm._assemble(conv, tools=None)  # noqa: SLF001
    assert "Git repository: yes" in parts.git_context
