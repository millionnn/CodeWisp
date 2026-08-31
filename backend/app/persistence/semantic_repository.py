"""Semantic documents / chunks / task summaries 持久化。"""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.app.memory.models import (
    CodeChunk,
    DocType,
    IndexStats,
    SemanticDocument,
    TaskRunSummary,
    new_semantic_chunk_id,
    new_semantic_doc_id,
    new_task_summary_id,
)
from backend.app.persistence._util import dumps_json, loads_json, utc_now_iso
from backend.app.persistence.store import SqliteStore


class SemanticIndexRepository:
    def __init__(self, store: SqliteStore) -> None:
        self._store = store

    def get_document(self, workspace: str, path: str) -> SemanticDocument | None:
        row = self._store.execute(
            "SELECT * FROM semantic_documents WHERE workspace=? AND path=?",
            (workspace, path),
        ).fetchone()
        return self._row_to_doc(row) if row else None

    def upsert_document(self, doc: SemanticDocument) -> SemanticDocument:
        now = utc_now_iso()
        doc.indexed_at = now
        self._store.execute(
            """
            INSERT INTO semantic_documents (
                id, workspace, path, doc_type, content_hash, mtime, size, indexed_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workspace, path) DO UPDATE SET
                doc_type=excluded.doc_type,
                content_hash=excluded.content_hash,
                mtime=excluded.mtime,
                size=excluded.size,
                indexed_at=excluded.indexed_at
            """,
            (
                doc.document_id,
                doc.workspace,
                doc.path,
                doc.doc_type.value,
                doc.content_hash,
                doc.mtime,
                doc.size,
                now,
            ),
        )
        # 冲突时保留原 id
        existing = self.get_document(doc.workspace, doc.path)
        self._store.commit()
        return existing or doc

    def delete_document(self, workspace: str, path: str) -> None:
        self._store.execute(
            "DELETE FROM semantic_documents WHERE workspace=? AND path=?",
            (workspace, path),
        )
        self._store.commit()

    def replace_chunks(self, document_id: str, chunks: list[CodeChunk]) -> None:
        self._store.execute(
            "DELETE FROM semantic_chunks WHERE document_id=?",
            (document_id,),
        )
        for ch in chunks:
            self._store.execute(
                """
                INSERT INTO semantic_chunks (
                    id, document_id, workspace, path, chunk_index,
                    start_line, end_line, content, content_hash, symbol,
                    embedding_json, embedding_dim, embedding_model, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    ch.chunk_id or new_semantic_chunk_id(),
                    document_id,
                    ch.workspace,
                    ch.path,
                    ch.chunk_index,
                    ch.start_line,
                    ch.end_line,
                    ch.content,
                    ch.content_hash,
                    ch.symbol,
                    dumps_json(ch.embedding) if ch.embedding is not None else None,
                    ch.embedding_dim,
                    ch.embedding_model,
                    utc_now_iso(),
                ),
            )
        self._store.commit()

    def list_chunks(self, workspace: str, *, limit: int = 5000) -> list[CodeChunk]:
        rows = self._store.execute(
            "SELECT * FROM semantic_chunks WHERE workspace=? LIMIT ?",
            (workspace, limit),
        ).fetchall()
        return [self._row_to_chunk(r) for r in rows]

    def list_chunks_for_path(self, workspace: str, path: str) -> list[CodeChunk]:
        rows = self._store.execute(
            "SELECT * FROM semantic_chunks WHERE workspace=? AND path=?",
            (workspace, path),
        ).fetchall()
        return [self._row_to_chunk(r) for r in rows]

    def delete_chunks_for_path(self, workspace: str, path: str) -> None:
        self._store.execute(
            "DELETE FROM semantic_chunks WHERE workspace=? AND path=?",
            (workspace, path),
        )
        self._store.commit()

    def set_meta(self, workspace: str, key: str, value: str) -> None:
        self._store.execute(
            """
            INSERT INTO embedding_metadata (id, workspace, key, value, updated_at)
            VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(workspace, key) DO UPDATE SET
                value=excluded.value,
                updated_at=excluded.updated_at
            """,
            (new_semantic_doc_id(), workspace, key, value, utc_now_iso()),
        )
        self._store.commit()

    def get_meta(self, workspace: str, key: str) -> str | None:
        row = self._store.execute(
            "SELECT value FROM embedding_metadata WHERE workspace=? AND key=?",
            (workspace, key),
        ).fetchone()
        return row["value"] if row else None

    def stats(self, workspace: str) -> IndexStats:
        docs = self._store.execute(
            "SELECT COUNT(*) AS c FROM semantic_documents WHERE workspace=?",
            (workspace,),
        ).fetchone()["c"]
        chunks = self._store.execute(
            "SELECT COUNT(*) AS c FROM semantic_chunks WHERE workspace=?",
            (workspace,),
        ).fetchone()["c"]
        memories = self._store.execute(
            "SELECT COUNT(*) AS c FROM memories WHERE invalidated=0 AND "
            "(workspace=? OR workspace IS NULL)",
            (workspace,),
        ).fetchone()["c"]
        summaries = self._store.execute(
            "SELECT COUNT(*) AS c FROM task_summaries WHERE workspace=?",
            (workspace,),
        ).fetchone()["c"]
        return IndexStats(
            workspace=workspace,
            documents=int(docs),
            chunks=int(chunks),
            memories=int(memories),
            task_summaries=int(summaries),
            embedding_model=self.get_meta(workspace, "embedding_model"),
        )

    def clear_workspace(self, workspace: str) -> None:
        self._store.execute(
            "DELETE FROM semantic_chunks WHERE workspace=?",
            (workspace,),
        )
        self._store.execute(
            "DELETE FROM semantic_documents WHERE workspace=?",
            (workspace,),
        )
        self._store.commit()

    def save_task_summary(self, summary: TaskRunSummary) -> TaskRunSummary:
        sid = summary.summary_id or new_task_summary_id()
        summary.summary_id = sid
        summary.created_at = summary.created_at or utc_now_iso()
        self._store.execute(
            """
            INSERT INTO task_summaries (
                id, session_id, agent_run_id, workspace, objective,
                summary_json, embedding_json, embedding_dim, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                sid,
                summary.session_id,
                summary.agent_run_id,
                summary.workspace,
                summary.objective,
                dumps_json(summary.to_summary_json()),
                dumps_json(summary.embedding) if summary.embedding else None,
                len(summary.embedding) if summary.embedding else None,
                summary.created_at,
            ),
        )
        self._store.commit()
        return summary

    def list_task_summaries(self, workspace: str, *, limit: int = 50) -> list[TaskRunSummary]:
        rows = self._store.execute(
            "SELECT * FROM task_summaries WHERE workspace=? ORDER BY created_at DESC LIMIT ?",
            (workspace, limit),
        ).fetchall()
        return [self._row_to_summary(r) for r in rows]

    def _row_to_doc(self, row: sqlite3.Row) -> SemanticDocument:
        return SemanticDocument(
            document_id=row["id"],
            workspace=row["workspace"],
            path=row["path"],
            doc_type=DocType(row["doc_type"]),
            content_hash=row["content_hash"],
            mtime=row["mtime"],
            size=row["size"],
            indexed_at=row["indexed_at"],
        )

    def _row_to_chunk(self, row: sqlite3.Row) -> CodeChunk:
        emb = loads_json(row["embedding_json"], default=None)
        return CodeChunk(
            chunk_id=row["id"],
            document_id=row["document_id"],
            workspace=row["workspace"],
            path=row["path"],
            chunk_index=row["chunk_index"],
            content=row["content"],
            content_hash=row["content_hash"],
            start_line=row["start_line"],
            end_line=row["end_line"],
            symbol=row["symbol"],
            embedding=list(emb) if isinstance(emb, list) else None,
            embedding_dim=row["embedding_dim"],
            embedding_model=row["embedding_model"],
        )

    def _row_to_summary(self, row: sqlite3.Row) -> TaskRunSummary:
        data = loads_json(row["summary_json"], default={}) or {}
        emb = loads_json(row["embedding_json"], default=None)
        return TaskRunSummary(
            summary_id=row["id"],
            session_id=row["session_id"],
            workspace=row["workspace"],
            objective=row["objective"],
            agent_run_id=row["agent_run_id"],
            changed_files=list(data.get("changed_files") or []),
            important_decisions=list(data.get("important_decisions") or []),
            tests=list(data.get("tests") or []),
            failures=list(data.get("failures") or []),
            final_result=str(data.get("final_result") or ""),
            unresolved_issues=list(data.get("unresolved_issues") or []),
            embedding=list(emb) if isinstance(emb, list) else None,
            created_at=row["created_at"],
        )
