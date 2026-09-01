"""GitContextProvider — Git metadata for Workspace Context."""

from __future__ import annotations

from backend.app.git.detector import GitDetector
from backend.app.git.models import GitRepositoryInfo, GitStatus
from backend.app.git.service import GitService
from backend.app.workspace.workspace import Workspace


class GitContextProvider:
    """Build Git metadata summary (no full diff)."""

    def __init__(self, workspace: Workspace | str) -> None:
        if isinstance(workspace, str):
            self._workspace = Workspace(workspace)
        else:
            self._workspace = workspace
        self._service = GitService(self._workspace)
        self._cached_text: str | None = None

    def refresh(self) -> str:
        self._cached_text = self.build_workspace_context()
        return self._cached_text

    @property
    def cached(self) -> str | None:
        return self._cached_text

    def build_workspace_context(self) -> str:
        info = GitDetector.detect(self._workspace.root)
        if not info.is_git_repository:
            return "## Git\n(not a git repository)"

        try:
            status = self._service._repo().status()  # noqa: SLF001
            commits = self._service._repo().log(limit=5)  # noqa: SLF001
        except Exception:  # noqa: BLE001
            return "## Git\n(repository detected, status unavailable)"

        return self._render(info, status, commits)

    @staticmethod
    def _render(
        info: GitRepositoryInfo,
        status: GitStatus,
        commits: list,
    ) -> str:
        lines = ["## Git"]
        lines.append(f"Git repository: yes")
        lines.append(f"root: {info.repository_root}")
        lines.append("")
        lines.append(f"Branch: {status.branch or '(detached)'}")
        if status.ahead or status.behind:
            lines.append(f"Tracking: ahead {status.ahead}, behind {status.behind}")
        lines.append("")
        lines.append("Working Tree:")
        lines.append(f"  modified: {status.modified_count}")
        lines.append(f"  staged: {status.staged_count}")
        lines.append(f"  untracked: {status.untracked_count}")
        if status.clean:
            lines.append("  clean: yes")

        changed = status.all_files
        if changed:
            lines.append("")
            lines.append("Changed files:")
            for f in changed[:20]:
                lines.append(f"  {f.display}")
            if len(changed) > 20:
                lines.append(f"  ... and {len(changed) - 20} more")

        if commits:
            lines.append("")
            lines.append("Recent commits:")
            for c in commits[:5]:
                lines.append(f"  {c.render_line()}")

        return "\n".join(lines)
