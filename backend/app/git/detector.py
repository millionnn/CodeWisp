"""Git repository detection — find .git root from workspace."""

from __future__ import annotations

from pathlib import Path

from backend.app.git.models import GitRepositoryInfo


# 检测Git仓库
class GitDetector:
    """Detect whether a workspace is inside a Git repository."""

    @staticmethod
    def detect(workspace_root: str | Path) -> GitRepositoryInfo:
        ws = Path(workspace_root).expanduser().resolve()
        if not ws.exists():
            return GitRepositoryInfo(
                is_git_repository=False,
                workspace=str(ws),
                repository_root=None,
            )

        current = ws
        while True:
            git_dir = current / ".git"
            if git_dir.exists():
                return GitRepositoryInfo(
                    is_git_repository=True,
                    workspace=str(ws),
                    repository_root=str(current),
                )
            parent = current.parent
            if parent == current:
                break
            current = parent

        return GitRepositoryInfo(
            is_git_repository=False,
            workspace=str(ws),
            repository_root=None,
        )
