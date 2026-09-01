"""Git test helpers."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path


def init_git_repo(root: Path, *, initial_commit: bool = True) -> None:
    """Initialize a git repo at root with optional initial commit."""
    env = {"GIT_TEMPLATE_DIR": ""}
    subprocess.run(
        ["git", "init"],
        cwd=str(root),
        check=True,
        capture_output=True,
        env={**os.environ, **env},
    )
    subprocess.run(
        ["git", "config", "user.email", "test@codewisp.local"],
        cwd=str(root),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "config", "user.name", "CodeWisp Test"],
        cwd=str(root),
        check=True,
        capture_output=True,
    )
    if initial_commit:
        (root / "README.md").write_text("# test\n", encoding="utf-8")
        subprocess.run(["git", "add", "README.md"], cwd=str(root), check=True, capture_output=True)
        subprocess.run(
            ["git", "commit", "-m", "initial"],
            cwd=str(root),
            check=True,
            capture_output=True,
        )


def git_commit_all(root: Path, message: str) -> None:
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", message],
        cwd=str(root),
        check=True,
        capture_output=True,
    )
