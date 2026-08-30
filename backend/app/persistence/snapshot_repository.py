"""Snapshot / FileChange SQLite Repository（V0.9 Phase 2）。"""

from __future__ import annotations

import sqlite3

from backend.app.changes.errors import SnapshotNotFoundError
from backend.app.changes.ids import new_file_change_id
from backend.app.changes.models import (
    ChangeType,
    FileChangeRecord,
    SnapshotFile,
    WorkspaceSnapshot,
)
from backend.app.persistence._util import utc_now_iso
from backend.app.persistence.errors import ConflictError, RepositoryError
from backend.app.persistence.store import SqliteStore

#持久化工作区的变动以及关联的文件变动
class SnapshotRepository:
    """持久化 WorkspaceSnapshot 与 FileChangeRecord。"""

    def __init__(self, store: SqliteStore) -> None:
        self._store = store

    def save_snapshot(self, snapshot: WorkspaceSnapshot) -> WorkspaceSnapshot:
        ts = snapshot.created_at or utc_now_iso()
        snap = snapshot if snapshot.created_at else WorkspaceSnapshot(
            snapshot_id=snapshot.snapshot_id,
            workspace_root=snapshot.workspace_root,
            reason=snapshot.reason,
            files=snapshot.files,
            session_id=snapshot.session_id,
            agent_run_id=snapshot.agent_run_id,
            agent_step_id=snapshot.agent_step_id,
            tool_call_id=snapshot.tool_call_id,
            created_at=ts,
        )
        try:
            self._store.execute(
                """
                INSERT INTO snapshots (
                    id, workspace_root, session_id, agent_run_id, agent_step_id,
                    tool_call_id, reason, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    snap.snapshot_id,
                    snap.workspace_root,
                    snap.session_id,
                    snap.agent_run_id,
                    snap.agent_step_id,
                    snap.tool_call_id,
                    snap.reason,
                    snap.created_at,
                ),
            )
            for item in snap.files:
                self._store.execute(
                    """
                    INSERT INTO snapshot_files (
                        snapshot_id, path, exists_flag, content, size, content_hash
                    ) VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        snap.snapshot_id,
                        item.path,
                        1 if item.exists else 0,
                        item.content,
                        item.size,
                        item.content_hash,
                    ),
                )
            self._store.commit()
        except sqlite3.IntegrityError as exc:
            raise ConflictError(f"Snapshot 冲突: {snap.snapshot_id}") from exc
        except sqlite3.Error as exc:
            raise RepositoryError(f"写入 Snapshot 失败: {exc}") from exc
        return snap

    def get_snapshot(self, snapshot_id: str) -> WorkspaceSnapshot:
        row = self._store.execute(
            "SELECT * FROM snapshots WHERE id = ?",
            (snapshot_id,),
        ).fetchone()
        if row is None:
            raise SnapshotNotFoundError(f"Snapshot 不存在: {snapshot_id}")
        files = self._load_files(snapshot_id)
        return _row_to_snapshot(row, files)

    def list_snapshots(
        self,
        *,
        agent_run_id: str | None = None,
        agent_step_id: str | None = None,
        tool_call_id: str | None = None,
        reason: str | None = None,
    ) -> list[WorkspaceSnapshot]:
        clauses: list[str] = []
        params: list[str] = []
        if agent_run_id is not None:
            clauses.append("agent_run_id = ?")
            params.append(agent_run_id)
        if agent_step_id is not None:
            clauses.append("agent_step_id = ?")
            params.append(agent_step_id)
        if tool_call_id is not None:
            clauses.append("tool_call_id = ?")
            params.append(tool_call_id)
        if reason is not None:
            clauses.append("reason = ?")
            params.append(reason)
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        rows = self._store.execute(
            f"SELECT * FROM snapshots{where} "
            "ORDER BY COALESCE(created_at, '') ASC, id ASC",
            tuple(params),
        ).fetchall()
        return [_row_to_snapshot(row, self._load_files(row["id"])) for row in rows]

    def add_file_change(
        self,
        *,
        session_id: str,
        agent_run_id: str,
        agent_step_id: str,
        path: str,
        change_type: ChangeType,
        tool_call_id: str | None = None,
        before_snapshot_id: str | None = None,
        after_snapshot_id: str | None = None,
        change_id: str | None = None,
        created_at: str | None = None,
    ) -> FileChangeRecord:
        cid = change_id or new_file_change_id()
        ts = created_at or utc_now_iso()
        try:
            self._store.execute(
                """
                INSERT INTO file_changes (
                    id, session_id, agent_run_id, agent_step_id, tool_call_id,
                    path, change_type, before_snapshot_id, after_snapshot_id, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    cid,
                    session_id,
                    agent_run_id,
                    agent_step_id,
                    tool_call_id,
                    path,
                    change_type.value,
                    before_snapshot_id,
                    after_snapshot_id,
                    ts,
                ),
            )
            self._store.commit()
        except sqlite3.IntegrityError as exc:
            raise ConflictError(f"FileChange 冲突: {cid}") from exc
        except sqlite3.Error as exc:
            raise RepositoryError(f"写入 FileChange 失败: {exc}") from exc
        return FileChangeRecord(
            change_id=cid,
            session_id=session_id,
            agent_run_id=agent_run_id,
            agent_step_id=agent_step_id,
            path=path,
            change_type=change_type,
            tool_call_id=tool_call_id,
            before_snapshot_id=before_snapshot_id,
            after_snapshot_id=after_snapshot_id,
            created_at=ts,
        )

    def list_file_changes(
        self,
        *,
        agent_run_id: str | None = None,
        agent_step_id: str | None = None,
        tool_call_id: str | None = None,
    ) -> list[FileChangeRecord]:
        if agent_run_id is None and agent_step_id is None and tool_call_id is None:
            raise ValueError("必须提供 agent_run_id / agent_step_id / tool_call_id 之一")
        clauses: list[str] = []
        params: list[str] = []
        if agent_run_id is not None:
            clauses.append("agent_run_id = ?")
            params.append(agent_run_id)
        if agent_step_id is not None:
            clauses.append("agent_step_id = ?")
            params.append(agent_step_id)
        if tool_call_id is not None:
            clauses.append("tool_call_id = ?")
            params.append(tool_call_id)
        rows = self._store.execute(
            "SELECT * FROM file_changes WHERE "
            + " AND ".join(clauses)
            + " ORDER BY COALESCE(created_at, '') ASC, id ASC",
            tuple(params),
        ).fetchall()
        return [_row_to_change(row) for row in rows]

    def get_step_boundary_snapshots(
        self, step_id: str
    ) -> tuple[WorkspaceSnapshot | None, WorkspaceSnapshot | None]:
        before = self.list_snapshots(agent_step_id=step_id, reason="pre_step")
        after = self.list_snapshots(agent_step_id=step_id, reason="post_step")
        return (
            before[0] if before else None,
            after[0] if after else None,
        )

    def _load_files(self, snapshot_id: str) -> tuple[SnapshotFile, ...]:
        rows = self._store.execute(
            """
            SELECT path, exists_flag, content, size, content_hash
            FROM snapshot_files WHERE snapshot_id = ?
            ORDER BY path ASC
            """,
            (snapshot_id,),
        ).fetchall()
        files: list[SnapshotFile] = []
        for row in rows:
            if int(row["exists_flag"]) == 1:
                files.append(
                    SnapshotFile(
                        path=row["path"],
                        exists=True,
                        content=row["content"] or "",
                        size=row["size"],
                        content_hash=row["content_hash"],
                    )
                )
            else:
                files.append(SnapshotFile.absent(row["path"]))
        return tuple(files)


def _row_to_snapshot(row: sqlite3.Row, files: tuple[SnapshotFile, ...]) -> WorkspaceSnapshot:
    return WorkspaceSnapshot(
        snapshot_id=row["id"],
        workspace_root=row["workspace_root"],
        reason=row["reason"],
        files=files,
        session_id=row["session_id"],
        agent_run_id=row["agent_run_id"],
        agent_step_id=row["agent_step_id"],
        tool_call_id=row["tool_call_id"],
        created_at=row["created_at"],
    )


def _row_to_change(row: sqlite3.Row) -> FileChangeRecord:
    return FileChangeRecord(
        change_id=row["id"],
        session_id=row["session_id"],
        agent_run_id=row["agent_run_id"],
        agent_step_id=row["agent_step_id"],
        path=row["path"],
        change_type=ChangeType(row["change_type"]),
        tool_call_id=row["tool_call_id"],
        before_snapshot_id=row["before_snapshot_id"],
        after_snapshot_id=row["after_snapshot_id"],
        created_at=row["created_at"],
    )
