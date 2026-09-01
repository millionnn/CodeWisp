"""Git domain service — repository detection, status, diff, log, branch, commit."""

from backend.app.git.errors import GitError, GitNotRepositoryError, GitOperationError
from backend.app.git.models import (
    CommitPreview,
    GitBranch,
    GitCommit,
    GitDiff,
    GitDiffFile,
    GitFileStatus,
    GitRepositoryInfo,
    GitStatus,
)
from backend.app.git.policy import GitPolicy, GitPolicyAction, GitPolicyDecision
from backend.app.git.service import GitService

__all__ = [
    "CommitPreview",
    "GitBranch",
    "GitCommit",
    "GitDiff",
    "GitDiffFile",
    "GitError",
    "GitFileStatus",
    "GitNotRepositoryError",
    "GitOperationError",
    "GitPolicy",
    "GitPolicyAction",
    "GitPolicyDecision",
    "GitRepositoryInfo",
    "GitService",
    "GitStatus",
]
