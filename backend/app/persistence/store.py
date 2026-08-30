"""SQLite 存储入口（V0.6 Phase 2-B）。

职责：连接管理、PRAGMA、自动 migration。
不包含领域 Repository / SessionService（Phase 2-C+）。

AgentLoop / Tools / Workspace 不得依赖本模块。
"""

from __future__ import annotations

import sqlite3
from pathlib import Path
from types import TracebackType
from typing import Self

from backend.app.persistence.errors import PersistenceError
from backend.app.persistence.migrate import apply_migrations, get_schema_version


class SqliteStore:
    """对单个 SQLite 数据库文件（或 ``:memory:``）的薄封装。"""

    def __init__(
        self,
        path: str | Path,
        *,
        migrate_on_connect: bool = True,
        migrations_dir: Path | None = None,
    ) -> None:
        self.path = path if path == ":memory:" else Path(path)
        self._migrate_on_connect = migrate_on_connect
        self._migrations_dir = migrations_dir
        self._conn: sqlite3.Connection | None = None

    @property
    def is_open(self) -> bool:
        return self._conn is not None

    def connect(self) -> sqlite3.Connection:
        """打开连接；必要时创建父目录并运行 migration。"""
        if self._conn is not None:
            return self._conn

        if self.path != ":memory:":
            assert isinstance(self.path, Path)
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
            except OSError as exc:
                raise PersistenceError(f"无法创建数据库目录: {exc}") from exc
            db_target: str | bytes = str(self.path)
        else:
            db_target = ":memory:"

        try:
            conn = sqlite3.connect(db_target, check_same_thread=False)
        except sqlite3.Error as exc:
            raise PersistenceError(f"无法打开 SQLite 数据库: {exc}") from exc

        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        # WAL 对文件库更友好；memory 忽略失败即可
        try:
            conn.execute("PRAGMA journal_mode = WAL")
        except sqlite3.Error:
            pass

        self._conn = conn
        if self._migrate_on_connect:
            apply_migrations(conn, directory=self._migrations_dir)
        return conn

    @property
    def connection(self) -> sqlite3.Connection:
        if self._conn is None:
            raise PersistenceError("SqliteStore 尚未 connect()")
        return self._conn

    def schema_version(self) -> int:
        return get_schema_version(self.connection)

    def execute(self, sql: str, parameters: tuple | list | dict = ()) -> sqlite3.Cursor:
        return self.connection.execute(sql, parameters)

    def executescript(self, sql: str) -> sqlite3.Cursor:
        return self.connection.executescript(sql)

    def commit(self) -> None:
        self.connection.commit()

    def close(self) -> None:
        if self._conn is not None:
            self._conn.close()
            self._conn = None

    def __enter__(self) -> Self:
        self.connect()
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        if exc is None:
            try:
                self.commit()
            except sqlite3.Error:
                pass
        self.close()
