"""GitRepository — lowest-level Git CLI boundary (shell=False only)."""

#
from __future__ import annotations

import re
import subprocess
from dataclasses import dataclass
from pathlib import Path

from backend.app.git.errors import GitOperationError
from backend.app.git.models import (
    GitBranch,
    GitCommit,
    GitDiff,
    GitDiffFile,
    GitFileChangeType,
    GitFileStatus,
    GitStatus,
)

DEFAULT_GIT_TIMEOUT = 30.0
LOG_FIELD_SEP = "\x1f"


@dataclass(frozen=True)
class GitCommandResult:
    stdout: str
    stderr: str
    exit_code: int

    @property
    def success(self) -> bool:
        return self.exit_code == 0


class GitRepository:
    """Execute git commands in a validated repository root."""

    def __init__(
        self,
        repository_root: str | Path,
        *,
        timeout: float = DEFAULT_GIT_TIMEOUT,
    ) -> None:
        self._root = Path(repository_root).expanduser().resolve()
        self._timeout = timeout

    @property
    def root(self) -> Path:
        return self._root

    def run(self, *args: str) -> GitCommandResult:
        cmd = ["git", *args]
        try:
            proc = subprocess.run(
                cmd,
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=self._timeout,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise GitOperationError(
                f"Git 命令超时（>{self._timeout}s）: git {' '.join(args)}"
            ) from exc
        except OSError as exc:
            raise GitOperationError(f"无法执行 git: {exc}") from exc

        return GitCommandResult(
            stdout=proc.stdout or "",
            stderr=proc.stderr or "",
            exit_code=proc.returncode,
        )

    def _require_ok(self, result: GitCommandResult, context: str) -> str:
        if result.success:
            return result.stdout
        msg = result.stderr.strip() or result.stdout.strip() or context
        raise GitOperationError(
            f"Git 操作失败: {msg}",
            exit_code=result.exit_code,
        )

    def status(self) -> GitStatus:
        out = self._require_ok(
            self.run("status", "--porcelain=v1", "-b"),
            "git status",
        )
        return _parse_porcelain_status(str(self._root), out)

    def diff(self, *, staged: bool = False, path: str | None = None) -> GitDiff:
        args = ["diff", "--numstat"]
        if staged:
            args.append("--staged")
        if path:
            args.extend(["--", path])
        numstat = self._require_ok(self.run(*args), "git diff --numstat")

        patch_args = ["diff"]
        if staged:
            patch_args.append("--staged")
        if path:
            patch_args.extend(["--", path])
        patch_out = self._require_ok(self.run(*patch_args), "git diff")

        files = _parse_numstat_and_patch(numstat, patch_out)
        return GitDiff(files=files, staged=staged)

    def log(self, *, limit: int = 20) -> list[GitCommit]:
        n = max(1, min(limit, 100))
        fmt = f"%H{LOG_FIELD_SEP}%h{LOG_FIELD_SEP}%an{LOG_FIELD_SEP}%aI{LOG_FIELD_SEP}%s"
        out = self._require_ok(
            self.run("log", f"-{n}", f"--format={fmt}"),
            "git log",
        )
        commits: list[GitCommit] = []
        for line in out.splitlines():
            if not line.strip():
                continue
            parts = line.split(LOG_FIELD_SEP, 4)
            if len(parts) < 5:
                continue
            commits.append(
                GitCommit(
                    commit_id=parts[0],
                    short_id=parts[1],
                    author=parts[2],
                    timestamp=parts[3],
                    message=parts[4],
                )
            )
        return commits

    def current_branch(self) -> str | None:
        result = self.run("rev-parse", "--abbrev-ref", "HEAD")
        if not result.success:
            return None
        name = result.stdout.strip()
        if name == "HEAD":
            return None
        return name

    def list_branches(self) -> list[GitBranch]:
        out = self._require_ok(
            self.run("branch", "--format=%(refname:short)"),
            "git branch",
        )
        current = self.current_branch()
        branches: list[GitBranch] = []
        for line in out.splitlines():
            name = line.strip()
            if name:
                branches.append(GitBranch(name=name, current=(name == current)))
        return branches

    def create_branch(self, name: str) -> GitBranch:
        self._require_ok(self.run("branch", name), f"git branch {name}")
        return GitBranch(name=name, current=False)

    def switch_branch(self, name: str) -> str:
        self._require_ok(self.run("switch", name), f"git switch {name}")
        return name

    def add(self, paths: list[str]) -> None:
        if not paths:
            self._require_ok(self.run("add", "-A"), "git add -A")
        else:
            self._require_ok(self.run("add", *paths), "git add")

    def commit(self, message: str) -> str:
        result = self.run("commit", "-m", message)
        if not result.success:
            msg = result.stderr.strip() or result.stdout.strip()
            raise GitOperationError(f"git commit 失败: {msg}", exit_code=result.exit_code)
        # Extract commit hash from output
        match = re.search(r"\[[\w/-]+\s+([0-9a-f]+)\]", result.stdout)
        if match:
            return match.group(1)
        rev = self.run("rev-parse", "HEAD")
        if rev.success:
            return rev.stdout.strip()[:7]
        return "unknown"

    def show(self, ref: str = "HEAD") -> str:
        return self._require_ok(self.run("show", ref), f"git show {ref}")


def _parse_porcelain_status(repository_root: str, output: str) -> GitStatus:
    branch: str | None = None
    ahead = 0
    behind = 0
    detached = False
    staged: list[GitFileStatus] = []
    unstaged: list[GitFileStatus] = []
    untracked: list[GitFileStatus] = []

    for line in output.splitlines():
        if line.startswith("## "):
            branch, ahead, behind, detached = _parse_branch_line(line[3:])
            continue
        if len(line) < 3:
            continue
        x, y = line[0], line[1]
        rest = line[3:]
        if not rest:
            continue

        old_path: str | None = None
        path = rest
        if " -> " in rest:
            old_path, path = rest.split(" -> ", 1)

        if x == "?" and y == "?":
            untracked.append(
                GitFileStatus(
                    path=path,
                    status=GitFileChangeType.UNTRACKED.value,
                    staged=False,
                    unstaged=True,
                )
            )
            continue

        status = _xy_to_status(x, y)
        fs = GitFileStatus(
            path=path,
            status=status,
            staged=(x not in {" ", "?"}),
            unstaged=(y not in {" ", "?"}),
            old_path=old_path,
        )
        if x != " ":
            staged.append(fs)
        if y != " ":
            unstaged.append(fs)

    clean = not staged and not unstaged and not untracked
    return GitStatus(
        repository_root=repository_root,
        branch=branch,
        ahead=ahead,
        behind=behind,
        staged=staged,
        unstaged=unstaged,
        untracked=untracked,
        clean=clean,
        detached=detached,
    )


def _parse_branch_line(line: str) -> tuple[str | None, int, int, bool]:
    """Parse ## branch...tracking [ahead N, behind M]"""
    branch: str | None = None
    ahead = 0
    behind = 0
    detached = False

    main_part = line
    bracket = ""
    if " [" in line:
        main_part, bracket = line.split(" [", 1)
        bracket = bracket.rstrip("]")

    if main_part.startswith("HEAD (no branch)"):
        detached = True
        branch = None
    elif "..." in main_part:
        branch = main_part.split("...", 1)[0].strip()
    else:
        branch = main_part.strip() or None

    if bracket:
        ahead_m = re.search(r"ahead\s+(\d+)", bracket)
        behind_m = re.search(r"behind\s+(\d+)", bracket)
        if ahead_m:
            ahead = int(ahead_m.group(1))
        if behind_m:
            behind = int(behind_m.group(1))

    return branch, ahead, behind, detached


def _xy_to_status(x: str, y: str) -> str:
    if x == "A" or y == "A":
        return GitFileChangeType.ADDED.value
    if x == "D" or y == "D":
        return GitFileChangeType.DELETED.value
    if x == "R" or y == "R":
        return GitFileChangeType.RENAMED.value
    if x == "C" or y == "C":
        return GitFileChangeType.COPIED.value
    return GitFileChangeType.MODIFIED.value


def _parse_numstat_and_patch(numstat: str, patch: str) -> list[GitDiffFile]:
    """Combine numstat lines with unified diff patches per file."""
    stats: dict[str, tuple[int, int]] = {}
    for line in numstat.splitlines():
        parts = line.split("\t")
        if len(parts) < 3:
            continue
        add_s, del_s, path = parts[0], parts[1], parts[2]
        additions = 0 if add_s == "-" else int(add_s)
        deletions = 0 if del_s == "-" else int(del_s)
        stats[path] = (additions, deletions)

    file_patches = _split_unified_diff(patch)
    files: list[GitDiffFile] = []
    all_paths = sorted(set(stats.keys()) | set(file_patches.keys()))
    for path in all_paths:
        additions, deletions = stats.get(path, (0, 0))
        file_patch = file_patches.get(path, "")
        change_type = GitFileChangeType.MODIFIED.value
        if additions > 0 and deletions == 0 and not file_patch:
            change_type = GitFileChangeType.ADDED.value
        elif deletions > 0 and additions == 0:
            change_type = GitFileChangeType.DELETED.value
        files.append(
            GitDiffFile(
                path=path,
                change_type=change_type,
                additions=additions,
                deletions=deletions,
                patch=file_patch,
            )
        )
    return files


def _split_unified_diff(patch: str) -> dict[str, str]:
    """Split combined unified diff into per-file patches."""
    if not patch.strip():
        return {}

    result: dict[str, str] = {}
    current_path: str | None = None
    current_lines: list[str] = []

    for line in patch.splitlines(keepends=True):
        if line.startswith("diff --git "):
            if current_path and current_lines:
                result[current_path] = "".join(current_lines)
            current_lines = [line]
            current_path = _extract_path_from_diff_header(line)
        elif line.startswith("+++ b/") and current_path is None:
            current_path = line[6:].strip()
            current_lines.append(line)
        else:
            current_lines.append(line)

    if current_path and current_lines:
        result[current_path] = "".join(current_lines)
    return result


def _extract_path_from_diff_header(line: str) -> str | None:
    # diff --git a/foo b/foo
    m = re.match(r"diff --git a/(.+?) b/(.+)", line.strip())
    if m:
        return m.group(2)
    return None
