"""SessionRepository：Session CRUD。"""

from __future__ import annotations

import sqlite3

from backend.app.persistence._util import utc_now_iso
from backend.app.persistence.errors import ConflictError, NotFoundError, RepositoryError
from backend.app.persistence.store import SqliteStore
from backend.app.session.models import Session


class SessionRepository:
    def __init__(self, store: SqliteStore) -> None:
        self._store = store

    def create(self, session: Session) -> Session:
        now = utc_now_iso()
        created = session
        if created.created_at is None or created.updated_at is None:
            created = Session(
                session_id=session.session_id,
                title=session.title,
                workspace=session.workspace,
                provider_id=session.provider_id,
                model_id=session.model_id,
                status=session.status,
                created_at=session.created_at or now,
                updated_at=session.updated_at or now,
            )
        try:
            self._store.execute(
                """
                INSERT INTO sessions (
                    id, title, workspace, provider_id, model_id,
                    status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created.session_id,
                    created.title,
                    created.workspace,
                    created.provider_id,
                    created.model_id,
                    created.status,
                    created.created_at,
                    created.updated_at,
                ),
            )
            self._store.commit()
        except sqlite3.IntegrityError as exc:
            raise ConflictError(f"Session 已存在: {created.session_id}") from exc
        except sqlite3.Error as exc:
            raise RepositoryError(f"创建 Session 失败: {exc}") from exc
        return created

    def get(self, session_id: str) -> Session:
        row = self._store.execute(
            "SELECT * FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Session 不存在: {session_id}")
        return _row_to_session(row)

    def list(self, *, limit: int = 100, offset: int = 0) -> list[Session]:
        if limit < 1:
            raise ValueError("limit 必须 >= 1")
        if offset < 0:
            raise ValueError("offset 必须 >= 0")
        rows = self._store.execute(
            """
            SELECT * FROM sessions
            ORDER BY COALESCE(updated_at, created_at, '') DESC, id DESC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
        return [_row_to_session(row) for row in rows]

    def update(
        self,
        session_id: str,
        *,
        title: str | None = None,
        status: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
        workspace: str | None = None,
    ) -> Session:
        current = self.get(session_id)
        updated = Session(
            session_id=current.session_id,
            title=title if title is not None else current.title,
            workspace=workspace if workspace is not None else current.workspace,
            provider_id=provider_id if provider_id is not None else current.provider_id,
            model_id=model_id if model_id is not None else current.model_id,
            status=status if status is not None else current.status,
            created_at=current.created_at,
            updated_at=utc_now_iso(),
        )
        try:
            self._store.execute(
                """
                UPDATE sessions SET
                    title = ?, workspace = ?, provider_id = ?, model_id = ?,
                    status = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    updated.title,
                    updated.workspace,
                    updated.provider_id,
                    updated.model_id,
                    updated.status,
                    updated.updated_at,
                    session_id,
                ),
            )
            self._store.commit()
        except sqlite3.Error as exc:
            raise RepositoryError(f"更新 Session 失败: {exc}") from exc
        return updated

    def rename(self, session_id: str, title: str) -> Session:
        return self.update(session_id, title=title)

    def delete(self, session_id: str) -> None:
        self.get(session_id)  # ensure exists
        try:
            self._store.execute("DELETE FROM sessions WHERE id = ?", (session_id,))
            self._store.commit()
        except sqlite3.Error as exc:
            raise RepositoryError(f"删除 Session 失败: {exc}") from exc


def _row_to_session(row: sqlite3.Row) -> Session:
    return Session(
        session_id=row["id"],
        title=row["title"],
        workspace=row["workspace"],
        provider_id=row["provider_id"],
        model_id=row["model_id"],
        status=row["status"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
