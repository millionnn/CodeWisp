"""Snapshot / Diff 领域模型（V0.9 Phase 1）。

仅内存表示与序列化；不访问 SQLite / Git。
"""

#确定快照状态的模型

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from enum import Enum
from typing import Any

from backend.app.changes.ids import new_snapshot_id

#要求字典中必须有某个键，且值为字符串
def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"缺少或非法字段: {key}")
    return value


def _optional_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"字段 {key} 必须是字符串或 None")
    return value


def content_sha256(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class ChangeType(str, Enum):
    ADDED = "ADDED"
    MODIFIED = "MODIFIED"
    DELETED = "DELETED"
    UNCHANGED = "UNCHANGED"


def _path_segments(path: str) -> list[str]:
    return [p for p in path.split("/") if p]


@dataclass(frozen=True)
class SnapshotFile:
    """单个文件在某一 Snapshot 中的状态。"""

    path: str
    exists: bool
    content: str | None = None
    size: int | None = None
    content_hash: str | None = None

    def __post_init__(self) -> None:
        if not self.path or self.path.startswith("/") or "\\" in self.path:
            raise ValueError(f"path 必须是非空的 workspace-relative POSIX 路径: {self.path!r}")
        if ".." in _path_segments(self.path):
            raise ValueError(f"path 不得包含 '..': {self.path!r}")
        if not self.exists:
            if self.content is not None or self.size is not None or self.content_hash is not None:
                raise ValueError("exists=False 时 content/size/content_hash 必须为 None")
        else:
            if self.content is None:
                raise ValueError("exists=True 时 content 不能为 None")
            if self.size is None:
                object.__setattr__(self, "size", len(self.content.encode("utf-8")))
            if self.content_hash is None:
                object.__setattr__(self, "content_hash", content_sha256(self.content))

    @classmethod
    def present(cls, path: str, content: str) -> SnapshotFile:
        return cls(
            path=path,
            exists=True,
            content=content,
            size=len(content.encode("utf-8")),
            content_hash=content_sha256(content),
        )

    @classmethod
    def absent(cls, path: str) -> SnapshotFile:
        return cls(path=path, exists=False, content=None, size=None, content_hash=None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "exists": self.exists,
            "content": self.content,
            "size": self.size,
            "content_hash": self.content_hash,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> SnapshotFile:
        if not isinstance(data, dict):
            raise TypeError("SnapshotFile.from_dict 需要 dict")
        exists = bool(data.get("exists"))
        return cls(
            path=_require_str(data, "path"),
            exists=exists,
            content=data.get("content") if exists else None,
            size=data.get("size") if exists else None,
            content_hash=data.get("content_hash") if exists else None,
        )


@dataclass(frozen=True)
class WorkspaceSnapshot:
    """某次工作区文件状态快照（显式 path 集合）。"""

    snapshot_id: str
    workspace_root: str
    reason: str
    files: tuple[SnapshotFile, ...]
    session_id: str | None = None
    agent_run_id: str | None = None
    agent_step_id: str | None = None
    tool_call_id: str | None = None
    created_at: str | None = None

    @classmethod
    def create(
        cls,
        *,
        workspace_root: str,
        files: list[SnapshotFile] | tuple[SnapshotFile, ...],
        reason: str = "manual",
        session_id: str | None = None,
        agent_run_id: str | None = None,
        agent_step_id: str | None = None,
        tool_call_id: str | None = None,
        snapshot_id: str | None = None,
        created_at: str | None = None,
    ) -> WorkspaceSnapshot:
        by_path = {f.path: f for f in files}
        ordered = tuple(by_path[k] for k in sorted(by_path))
        return cls(
            snapshot_id=snapshot_id or new_snapshot_id(),
            workspace_root=workspace_root,
            reason=reason,
            files=ordered,
            session_id=session_id,
            agent_run_id=agent_run_id,
            agent_step_id=agent_step_id,
            tool_call_id=tool_call_id,
            created_at=created_at,
        )

    def file_map(self) -> dict[str, SnapshotFile]:
        return {f.path: f for f in self.files}

    def to_dict(self) -> dict[str, Any]:
        return {
            "snapshot_id": self.snapshot_id,
            "workspace_root": self.workspace_root,
            "reason": self.reason,
            "files": [f.to_dict() for f in self.files],
            "session_id": self.session_id,
            "agent_run_id": self.agent_run_id,
            "agent_step_id": self.agent_step_id,
            "tool_call_id": self.tool_call_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> WorkspaceSnapshot:
        if not isinstance(data, dict):
            raise TypeError("WorkspaceSnapshot.from_dict 需要 dict")
        raw_files = data.get("files") or []
        if not isinstance(raw_files, list):
            raise ValueError("files 必须是 list")
        files = [SnapshotFile.from_dict(item) for item in raw_files]
        return cls(
            snapshot_id=_require_str(data, "snapshot_id"),
            workspace_root=_require_str(data, "workspace_root"),
            reason=str(data.get("reason") or "manual"),
            files=tuple(files),
            session_id=_optional_str(data, "session_id"),
            agent_run_id=_optional_str(data, "agent_run_id"),
            agent_step_id=_optional_str(data, "agent_step_id"),
            tool_call_id=_optional_str(data, "tool_call_id"),
            created_at=_optional_str(data, "created_at"),
        )


@dataclass(frozen=True)
class FileChangeRecord:
    """一次写工具导致的文件变更（可持久化）。"""

    change_id: str
    session_id: str
    agent_run_id: str
    agent_step_id: str
    path: str
    change_type: ChangeType
    tool_call_id: str | None = None
    before_snapshot_id: str | None = None
    after_snapshot_id: str | None = None
    created_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_id": self.change_id,
            "session_id": self.session_id,
            "agent_run_id": self.agent_run_id,
            "agent_step_id": self.agent_step_id,
            "tool_call_id": self.tool_call_id,
            "path": self.path,
            "change_type": self.change_type.value,
            "before_snapshot_id": self.before_snapshot_id,
            "after_snapshot_id": self.after_snapshot_id,
            "created_at": self.created_at,
        }


@dataclass(frozen=True)
class FileDiff:
    path: str
    change_type: ChangeType
    before: str | None
    after: str | None

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "change_type": self.change_type.value,
            "before": self.before,
            "after": self.after,
        }


@dataclass(frozen=True)
class RestoreReport:
    """多文件 restore 的 best-effort 报告（非事务）。"""

    snapshot_id: str
    applied: tuple[str, ...]
    failed: tuple[tuple[str, str], ...]  # (path, error)

    @property
    def ok(self) -> bool:
        return len(self.failed) == 0


@dataclass(frozen=True)
class RevertReport:
    """一次 revert step/run 的结果（不删除历史记录）。"""

    target_type: str  # "step" | "run"
    target_id: str
    safety_snapshot_id: str | None
    restored_snapshot_ids: tuple[str, ...]
    applied: tuple[str, ...]
    failed: tuple[tuple[str, str], ...]
    denied: bool = False

    @property
    def ok(self) -> bool:
        return (not self.denied) and len(self.failed) == 0
