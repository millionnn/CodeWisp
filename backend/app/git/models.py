"""Git domain models — structured, machine-readable."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


# 文件变更类型
class GitFileChangeType(str, Enum):
    ADDED = "added"
    MODIFIED = "modified"
    DELETED = "deleted"
    RENAMED = "renamed"
    UNTRACKED = "untracked"
    COPIED = "copied"


# Git仓库信息
@dataclass(frozen=True)
class GitRepositoryInfo:
    """Repository detection result."""

    is_git_repository: bool
    workspace: str
    repository_root: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "is_git_repository": self.is_git_repository,
            "workspace": self.workspace,
            "repository_root": self.repository_root,
        }


# 文件状态
@dataclass(frozen=True)
class GitFileStatus:
    path: str
    status: str
    staged: bool = False
    unstaged: bool = False
    old_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {
            "path": self.path,
            "status": self.status,
            "staged": self.staged,
            "unstaged": self.unstaged,
        }
        if self.old_path:
            data["old_path"] = self.old_path
        return data

    @property
    def display(self) -> str:
        """Short status prefix for CLI."""
        if self.status == GitFileChangeType.UNTRACKED.value:
            return f"?? {self.path}"
        prefix = ""
        if self.staged:
            if self.status == GitFileChangeType.ADDED.value:
                prefix = "A "
            elif self.status == GitFileChangeType.DELETED.value:
                prefix = "D "
            elif self.status == GitFileChangeType.RENAMED.value:
                prefix = "R "
            else:
                prefix = "M "
        elif self.unstaged:
            prefix = " M" if self.status != GitFileChangeType.UNTRACKED.value else "??"
        return f"{prefix}{self.path}".strip()


# Git状态
@dataclass
class GitStatus:
    repository_root: str
    branch: str | None = None
    ahead: int = 0
    behind: int = 0
    staged: list[GitFileStatus] = field(default_factory=list)
    unstaged: list[GitFileStatus] = field(default_factory=list)
    untracked: list[GitFileStatus] = field(default_factory=list)
    clean: bool = True
    detached: bool = False

    @property
    def modified_count(self) -> int:
        return len(self.unstaged) + len(
            [f for f in self.staged if f.status == GitFileChangeType.MODIFIED.value]
        )

    @property
    def staged_count(self) -> int:
        return len(self.staged)

    @property
    def untracked_count(self) -> int:
        return len(self.untracked)

    @property
    def all_files(self) -> list[GitFileStatus]:
        seen: dict[str, GitFileStatus] = {}
        for group in (self.staged, self.unstaged, self.untracked):
            for f in group:
                seen[f.path] = f
        return list(seen.values())

    def to_dict(self) -> dict[str, Any]:
        return {
            "repository_root": self.repository_root,
            "branch": self.branch,
            "ahead": self.ahead,
            "behind": self.behind,
            "clean": self.clean,
            "detached": self.detached,
            "modified_count": self.modified_count,
            "staged_count": self.staged_count,
            "untracked_count": self.untracked_count,
            "staged": [f.to_dict() for f in self.staged],
            "unstaged": [f.to_dict() for f in self.unstaged],
            "untracked": [f.to_dict() for f in self.untracked],
            "files": [f.to_dict() for f in self.all_files],
        }

    def render_summary(self) -> str:
        lines = [
            f"Repository: {self.repository_root}",
            f"Branch: {self.branch or '(detached)'}",
        ]
        if self.ahead or self.behind:
            lines.append(f"Tracking: ahead {self.ahead}, behind {self.behind}")
        lines.append(
            f"Status: modified={self.modified_count}, "
            f"staged={self.staged_count}, untracked={self.untracked_count}"
        )
        if self.clean:
            lines.append("Working tree: clean")
        else:
            lines.append("Files:")
            for f in self.all_files[:30]:
                lines.append(f"  {f.display}")
            if len(self.all_files) > 30:
                lines.append(f"  ... and {len(self.all_files) - 30} more")
        return "\n".join(lines)


@dataclass(frozen=True)
class GitDiffFile:
    path: str
    change_type: str
    additions: int
    deletions: int
    patch: str
    old_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = {
            "path": self.path,
            "change_type": self.change_type,
            "additions": self.additions,
            "deletions": self.deletions,
            "patch": self.patch,
        }
        if self.old_path:
            data["old_path"] = self.old_path
        return data


@dataclass
class GitDiff:
    files: list[GitDiffFile] = field(default_factory=list)
    staged: bool = False

    @property
    def total_additions(self) -> int:
        return sum(f.additions for f in self.files)

    @property
    def total_deletions(self) -> int:
        return sum(f.deletions for f in self.files)

    @property
    def patch(self) -> str:
        return "\n".join(f.patch for f in self.files if f.patch)

    def to_dict(self) -> dict[str, Any]:
        return {
            "staged": self.staged,
            "total_additions": self.total_additions,
            "total_deletions": self.total_deletions,
            "files": [f.to_dict() for f in self.files],
            "patch": self.patch,
        }

    def render_summary(self) -> str:
        lines = [
            f"Diff ({'staged' if self.staged else 'working tree'}): "
            f"+{self.total_additions} -{self.total_deletions}",
        ]
        for f in self.files:
            lines.append(f"  {f.path} (+{f.additions}/-{f.deletions})")
        return "\n".join(lines)


@dataclass(frozen=True)
class GitCommit:
    commit_id: str
    short_id: str
    author: str
    timestamp: str
    message: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "commit_id": self.commit_id,
            "short_id": self.short_id,
            "author": self.author,
            "timestamp": self.timestamp,
            "message": self.message,
        }

    def render_line(self) -> str:
        return f"{self.short_id} {self.message}"


@dataclass(frozen=True)
class GitBranch:
    name: str
    current: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"name": self.name, "current": self.current}


@dataclass
class CommitPreview:
    branch: str | None
    files: list[str] = field(default_factory=list)
    additions: int = 0
    deletions: int = 0
    message: str = ""
    staged: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "branch": self.branch,
            "files": list(self.files),
            "additions": self.additions,
            "deletions": self.deletions,
            "message": self.message,
            "staged": self.staged,
        }

    def render(self) -> str:
        lines = ["Commit preview", ""]
        lines.append(f"Branch: {self.branch or '(detached)'}")
        lines.append("")
        lines.append("Changes:")
        for p in self.files:
            lines.append(f"  {p}")
        lines.append("")
        lines.append(f"+{self.additions}")
        lines.append(f"-{self.deletions}")
        lines.append("")
        lines.append(f"Message:")
        lines.append(self.message)
        return "\n".join(lines)
