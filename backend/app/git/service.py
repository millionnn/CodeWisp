"""GitService — high-level Git operations for Agent / API / CLI."""

from __future__ import annotations

from pathlib import Path

from backend.app.git.detector import GitDetector
from backend.app.git.errors import GitNotRepositoryError, GitOperationError
from backend.app.git.models import (
    CommitPreview,
    GitBranch,
    GitCommit,
    GitDiff,
    GitRepositoryInfo,
    GitStatus,
)
from backend.app.git.policy import GitPolicy, GitPolicyAction, GitPolicyDecision
from backend.app.git.repository import GitRepository
from backend.app.workspace.errors import PathOutsideWorkspaceError
from backend.app.workspace.workspace import Workspace


class GitService:
    """Domain service: detect, status, diff, log, branch, commit."""

    def __init__(
        self,
        workspace: Workspace,
        *,
        policy: GitPolicy | None = None,
    ) -> None:
        self._workspace = workspace
        self._policy = policy or GitPolicy()

    @property
    def workspace(self) -> Workspace:
        return self._workspace

    def detect(self) -> GitRepositoryInfo:
        return GitDetector.detect(self._workspace.root)

    def _repo(self) -> GitRepository:
        info = self.detect()
        if not info.is_git_repository or not info.repository_root:
            raise GitNotRepositoryError(
                f"工作区 {self._workspace.root} 不是 Git 仓库。"
            )
        return GitRepository(info.repository_root)

    def _validate_path_in_workspace(self, path: str) -> str:
        """Ensure git path argument stays within workspace boundary."""
        resolved = self._workspace.resolve_path(path)
        return self._workspace.relative_to_root(resolved)

    def policy_decide(self, subcommand: str, args: tuple[str, ...] | list[str] = ()) -> GitPolicyDecision:
        return self._policy.decide(subcommand, args)

    def status(self) -> GitStatus | GitRepositoryInfo:
        info = self.detect()
        if not info.is_git_repository:
            return info
        return self._repo().status()

    def diff(
        self,
        *,
        path: str | None = None,
        staged: bool = False,
    ) -> GitDiff:
        repo = self._repo()
        rel_path: str | None = None
        if path:
            rel_path = self._validate_path_in_workspace(path)
        return repo.diff(staged=staged, path=rel_path)

    def diff_file(self, path: str, *, staged: bool = False) -> GitDiff:
        return self.diff(path=path, staged=staged)

    def diff_staged(self) -> GitDiff:
        return self.diff(staged=True)

    def log(self, *, limit: int = 20) -> list[GitCommit]:
        return self._repo().log(limit=limit)

    def list_branches(self) -> list[GitBranch]:
        return self._repo().list_branches()

    def current_branch(self) -> str | None:
        return self._repo().current_branch()

    def create_branch(self, name: str) -> GitBranch:
        if not name or not name.strip():
            raise GitOperationError("分支名不能为空。")
        decision = self._policy.decide("branch", [name])
        if decision.action is GitPolicyAction.DENY:
            raise GitOperationError(decision.reason)
        return self._repo().create_branch(name.strip())

    def switch_branch(self, name: str) -> str:
        if not name or not name.strip():
            raise GitOperationError("分支名不能为空。")
        decision = self._policy.decide("switch", [name.strip()])
        if decision.action is GitPolicyAction.DENY:
            raise GitOperationError(decision.reason)
        return self._repo().switch_branch(name.strip())

    def show(self, ref: str = "HEAD") -> str:
        return self._repo().show(ref)

    def build_commit_preview(
        self,
        message: str,
        paths: list[str] | None = None,
    ) -> CommitPreview:
        """Inspect status + diff before commit."""
        status = self._repo().status()
        diff = self.diff(staged=False)
        if paths:
            validated = [self._validate_path_in_workspace(p) for p in paths]
            diff_files = [f for f in diff.files if f.path in validated]
            file_paths = validated
        else:
            diff_files = diff.files
            file_paths = [f.path for f in status.all_files]

        preview = CommitPreview(
            branch=status.branch,
            files=file_paths,
            additions=sum(f.additions for f in diff_files),
            deletions=sum(f.deletions for f in diff_files),
            message=message,
            staged=False,
        )
        return preview

    def commit(
        self,
        message: str,
        paths: list[str] | None = None,
    ) -> dict[str, str]:
        """Stage and commit. Caller must handle permission before calling."""
        if not message or not message.strip():
            raise GitOperationError("commit message 不能为空。")

        repo = self._repo()
        if paths:
            validated = [self._validate_path_in_workspace(p) for p in paths]
            repo.add(validated)
        else:
            repo.add([])

        commit_id = repo.commit(message.strip())
        branch = repo.current_branch()
        return {
            "commit_id": commit_id,
            "branch": branch or "",
            "message": message.strip(),
            "paths": paths or [],
        }

    @staticmethod
    def for_workspace_root(root: str | Path) -> GitService:
        return GitService(Workspace(root))
