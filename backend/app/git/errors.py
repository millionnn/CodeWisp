"""Git domain errors."""

from __future__ import annotations


class GitError(Exception):
    """Git 领域基础异常。"""


class GitNotRepositoryError(GitError):
    """工作区不在 Git 仓库内。"""


class GitOperationError(GitError):
    """Git 命令执行失败。"""

    def __init__(self, message: str, *, exit_code: int | None = None) -> None:
        super().__init__(message)
        self.exit_code = exit_code


class GitPolicyDeniedError(GitError):
    """Git 策略拒绝执行。"""
