"""ConversationRepository：按 Session 追加 / 加载消息。"""

from __future__ import annotations

import sqlite3

from backend.app.llm.messages import Conversation, Message
from backend.app.llm.response import ToolCall
from backend.app.persistence._util import dumps_json, loads_json, utc_now_iso
from backend.app.persistence.errors import ConflictError, NotFoundError, RepositoryError
from backend.app.persistence.store import SqliteStore
from backend.app.session.ids import new_message_id


class ConversationRepository:
    def __init__(self, store: SqliteStore) -> None:
        self._store = store

    def _ensure_session(self, session_id: str) -> None:
        row = self._store.execute(
            "SELECT 1 FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Session 不存在: {session_id}")

    def next_seq(self, session_id: str) -> int:
        self._ensure_session(session_id)
        row = self._store.execute(
            "SELECT COALESCE(MAX(seq), 0) AS max_seq FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["max_seq"]) + 1

    def append_message(self, session_id: str, message: Message) -> Message:
        """追加一条消息；自动补齐 message_id / seq / session_id / created_at。"""
        self._ensure_session(session_id)
        seq = message.seq if message.seq is not None else self.next_seq(session_id)
        stored = message.with_persistence_meta(
            message_id=message.message_id or new_message_id(),
            session_id=session_id,
            seq=seq,
            created_at=message.created_at or utc_now_iso(),
            agent_run_id=message.agent_run_id,
            step_id=message.step_id,
        )
        # with_persistence_meta 对 None agent_run_id 会保留原值；显式再构一次确保 session_id
        stored = Message(
            role=stored.role,
            content=stored.content,
            tool_calls=tuple(tc.with_stable_id() for tc in stored.tool_calls),
            tool_call_id=stored.tool_call_id,
            message_id=stored.message_id,
            session_id=session_id,
            agent_run_id=stored.agent_run_id,
            step_id=stored.step_id,
            seq=stored.seq,
            created_at=stored.created_at,
        )
        tool_calls_json = (
            dumps_json([tc.to_persistence_dict() for tc in stored.tool_calls])
            if stored.tool_calls
            else None
        )
        try:
            self._store.execute(
                """
                INSERT INTO messages (
                    id, session_id, agent_run_id, step_id, seq, role, content,
                    tool_call_id, tool_calls_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stored.message_id,
                    stored.session_id,
                    stored.agent_run_id,
                    stored.step_id,
                    stored.seq,
                    stored.role,
                    stored.content,
                    stored.tool_call_id,
                    tool_calls_json,
                    stored.created_at,
                ),
            )
            self._store.commit()
        except sqlite3.IntegrityError as exc:
            raise ConflictError(
                f"追加消息冲突 (session={session_id}, seq={stored.seq}): {exc}"
            ) from exc
        except sqlite3.Error as exc:
            raise RepositoryError(f"追加消息失败: {exc}") from exc
        return stored

    def list_messages(self, session_id: str) -> list[Message]:
        self._ensure_session(session_id)
        rows = self._store.execute(
            """
            SELECT * FROM messages
            WHERE session_id = ?
            ORDER BY seq ASC, created_at ASC, id ASC
            """,
            (session_id,),
        ).fetchall()
        return [_row_to_message(row) for row in rows]

    def load_conversation(self, session_id: str) -> Conversation:
        return Conversation(messages=self.list_messages(session_id))

    def count_messages(self, session_id: str) -> int:
        self._ensure_session(session_id)
        row = self._store.execute(
            "SELECT COUNT(*) AS n FROM messages WHERE session_id = ?",
            (session_id,),
        ).fetchone()
        return int(row["n"])


def _row_to_message(row: sqlite3.Row) -> Message:
    raw_calls = loads_json(row["tool_calls_json"], default=[])
    if raw_calls is None:
        raw_calls = []
    if not isinstance(raw_calls, list):
        raise RepositoryError(f"messages.tool_calls_json 非法: {row['id']}")
    tool_calls = tuple(
        ToolCall.from_persistence_dict(item).with_stable_id() for item in raw_calls
    )
    return Message(
        role=row["role"],
        content=row["content"],
        tool_calls=tool_calls,
        tool_call_id=row["tool_call_id"],
        message_id=row["id"],
        session_id=row["session_id"],
        agent_run_id=row["agent_run_id"],
        step_id=row["step_id"],
        seq=row["seq"],
        created_at=row["created_at"],
    )
