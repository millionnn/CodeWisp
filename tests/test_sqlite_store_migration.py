"""V0.6 Phase 2-B：SqliteStore + migration 测试。"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from backend.app.persistence.errors import MigrationError, PersistenceError
from backend.app.persistence.migrate import (
    apply_migrations,
    get_schema_version,
    load_migrations,
)
from backend.app.persistence.store import SqliteStore


EXPECTED_TABLES = {
    "schema_migrations",
    "sessions",
    "messages",
    "agent_runs",
    "agent_steps",
    "tool_calls",
    "snapshots",
    "snapshot_files",
    "file_changes",
    "task_states",
    "plans",
    "plan_steps",
    "memories",
    "context_checkpoints",
    "memory_sources",
    "semantic_documents",
    "semantic_chunks",
    "embedding_metadata",
    "task_summaries",
}


def _table_names(conn: sqlite3.Connection) -> set[str]:
    rows = conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
    ).fetchall()
    return {row[0] for row in rows}


def test_package_migrations_include_v1() -> None:
    migrations = load_migrations()
    assert migrations
    assert migrations[0].version == 1
    assert "sessions" in migrations[0].sql
    assert any(m.version == 2 for m in migrations)
    assert "snapshots" in next(m.sql for m in migrations if m.version == 2)
    assert any(m.version == 3 for m in migrations)
    assert "task_states" in next(m.sql for m in migrations if m.version == 3)
    assert any(m.version == 4 for m in migrations)
    assert "semantic_chunks" in next(m.sql for m in migrations if m.version == 4)


def test_sqlite_store_memory_applies_v1_schema() -> None:
    with SqliteStore(":memory:") as store:
        assert store.schema_version() == 4
        tables = _table_names(store.connection)
        assert EXPECTED_TABLES.issubset(tables)


def test_sqlite_store_file_migrate_and_reopen(tmp_path: Path) -> None:
    db_path = tmp_path / "codewisp.db"
    with SqliteStore(db_path) as store:
        assert store.schema_version() == 4
        store.execute(
            "INSERT INTO sessions (id, title, workspace, provider_id, model_id, status) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("ses_1", "t", "/ws", "deepseek", "deepseek-chat", "active"),
        )

    # 模拟进程重启：重新打开同一文件，migration 幂等，数据仍在
    with SqliteStore(db_path) as store:
        assert store.schema_version() == 4
        newly = apply_migrations(store.connection)
        assert newly == []
        row = store.execute(
            "SELECT title, workspace, provider_id, model_id FROM sessions WHERE id=?",
            ("ses_1",),
        ).fetchone()
        assert row is not None
        assert tuple(row) == ("t", "/ws", "deepseek", "deepseek-chat")


def test_migration_idempotent_on_connect(tmp_path: Path) -> None:
    db_path = tmp_path / "idem.db"
    store = SqliteStore(db_path)
    store.connect()
    v1 = store.schema_version()
    apply_migrations(store.connection)
    assert store.schema_version() == v1
    store.close()


def test_schema_has_provider_model_and_identity_columns() -> None:
    with SqliteStore(":memory:") as store:
        session_cols = {
            row[1]
            for row in store.execute("PRAGMA table_info(sessions)").fetchall()
        }
        assert {"id", "workspace", "provider_id", "model_id"}.issubset(session_cols)

        run_cols = {
            row[1]
            for row in store.execute("PRAGMA table_info(agent_runs)").fetchall()
        }
        assert {
            "id",
            "session_id",
            "provider_id",
            "model_id",
            "status",
            "termination_reason",
        }.issubset(run_cols)

        step_cols = {
            row[1]
            for row in store.execute("PRAGMA table_info(agent_steps)").fetchall()
        }
        assert {"id", "agent_run_id", "session_id", "step_index"}.issubset(step_cols)

        msg_cols = {
            row[1]
            for row in store.execute("PRAGMA table_info(messages)").fetchall()
        }
        assert {
            "id",
            "session_id",
            "agent_run_id",
            "step_id",
            "seq",
            "role",
            "tool_calls_json",
            "tool_call_id",
        }.issubset(msg_cols)

        tc_cols = {
            row[1]
            for row in store.execute("PRAGMA table_info(tool_calls)").fetchall()
        }
        assert {
            "id",
            "step_id",
            "tool_name",
            "arguments_json",
            "arguments_raw",
            "parse_error",
            "result_json",
        }.issubset(tc_cols)


def test_foreign_keys_cascade_session_delete() -> None:
    with SqliteStore(":memory:") as store:
        store.execute(
            "INSERT INTO sessions (id, title, workspace, provider_id, model_id) "
            "VALUES ('ses_a', 'A', '/a', 'deepseek', 'deepseek-chat')"
        )
        store.execute(
            "INSERT INTO agent_runs "
            "(id, session_id, provider_id, model_id, status) "
            "VALUES ('run_1', 'ses_a', 'deepseek', 'deepseek-chat', 'completed')"
        )
        store.execute(
            "INSERT INTO agent_steps "
            "(id, agent_run_id, session_id, step_index, status) "
            "VALUES ('step_1', 'run_1', 'ses_a', 1, 'completed')"
        )
        store.execute(
            "INSERT INTO messages "
            "(id, session_id, agent_run_id, step_id, seq, role, content) "
            "VALUES ('msg_1', 'ses_a', 'run_1', 'step_1', 1, 'user', 'hi')"
        )
        store.execute(
            "INSERT INTO tool_calls "
            "(id, session_id, agent_run_id, step_id, tool_name, arguments_json) "
            "VALUES ('tc_1', 'ses_a', 'run_1', 'step_1', 'edit_file', '{}')"
        )
        store.commit()

        store.execute("DELETE FROM sessions WHERE id='ses_a'")
        store.commit()

        assert store.execute("SELECT COUNT(*) FROM agent_runs").fetchone()[0] == 0
        assert store.execute("SELECT COUNT(*) FROM agent_steps").fetchone()[0] == 0
        assert store.execute("SELECT COUNT(*) FROM messages").fetchone()[0] == 0
        assert store.execute("SELECT COUNT(*) FROM tool_calls").fetchone()[0] == 0


def test_custom_migrations_dir(tmp_path: Path) -> None:
    mig_dir = tmp_path / "migs"
    mig_dir.mkdir()
    (mig_dir / "001_boot.sql").write_text(
        "CREATE TABLE IF NOT EXISTS ping (id INTEGER PRIMARY KEY);",
        encoding="utf-8",
    )
    (mig_dir / "002_pong.sql").write_text(
        "CREATE TABLE IF NOT EXISTS pong (id INTEGER PRIMARY KEY);",
        encoding="utf-8",
    )

    db_path = tmp_path / "custom.db"
    with SqliteStore(db_path, migrations_dir=mig_dir) as store:
        assert store.schema_version() == 2
        tables = _table_names(store.connection)
        assert "ping" in tables and "pong" in tables

    # 再开一次只应用增量（无）
    with SqliteStore(db_path, migrations_dir=mig_dir) as store:
        assert apply_migrations(store.connection, directory=mig_dir) == []
        assert store.schema_version() == 2


def test_invalid_migration_filename_raises(tmp_path: Path) -> None:
    mig_dir = tmp_path / "bad"
    mig_dir.mkdir()
    (mig_dir / "not_a_migration.sql").write_text("SELECT 1;", encoding="utf-8")
    with pytest.raises(MigrationError, match="非法 migration"):
        load_migrations(mig_dir)


def test_store_requires_connect_before_connection_property() -> None:
    store = SqliteStore(":memory:", migrate_on_connect=False)
    with pytest.raises(PersistenceError, match="尚未 connect"):
        _ = store.connection


def test_relation_smoke_insert_graph() -> None:
    """验证 Session→Run→Step→Message→ToolCall 外键能写入（非 Repository）。"""
    with SqliteStore(":memory:") as store:
        store.execute(
            "INSERT INTO sessions (id, title, workspace, provider_id, model_id) "
            "VALUES ('ses_1', 'Demo', '/ws', 'deepseek', 'deepseek-chat')"
        )
        store.execute(
            "INSERT INTO agent_runs "
            "(id, session_id, provider_id, model_id, status, termination_reason, max_steps) "
            "VALUES ('run_1', 'ses_1', 'deepseek', 'deepseek-chat', 'completed', 'completed', 15)"
        )
        store.execute(
            "INSERT INTO agent_steps "
            "(id, agent_run_id, session_id, step_index) "
            "VALUES ('step_1', 'run_1', 'ses_1', 1)"
        )
        store.execute(
            "INSERT INTO messages "
            "(id, session_id, agent_run_id, step_id, seq, role, content, tool_calls_json) "
            "VALUES ('msg_1', 'ses_1', 'run_1', 'step_1', 1, 'assistant', NULL, '[]')"
        )
        store.execute(
            "INSERT INTO tool_calls "
            "(id, session_id, agent_run_id, step_id, tool_name, arguments_json, result_json) "
            "VALUES ('tc_1', 'ses_1', 'run_1', 'step_1', 'edit_file', "
            "'{\"path\":\"a.py\"}', '{\"success\":true}')"
        )
        store.commit()

        assert get_schema_version(store.connection) == 4
        n = store.execute(
            "SELECT COUNT(*) FROM tool_calls WHERE step_id='step_1'"
        ).fetchone()[0]
        assert n == 1
