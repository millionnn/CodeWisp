"""简单 versioned SQLite migration（无 Alembic）。

约定：
- migrations/ 下文件名为 ``NNN_name.sql``（NNN 为整数版本）
- ``schema_migrations`` 记录已应用 version
- 按 version 升序执行未应用脚本；禁止删库升级
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from importlib import resources
from pathlib import Path

from backend.app.persistence.errors import MigrationError

_MIGRATION_NAME_RE = re.compile(r"^(\d+)_(.+)\.sql$", re.IGNORECASE)


@dataclass(frozen=True)
class Migration:
    version: int
    name: str
    sql: str
    source: str


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _parse_migration_filename(filename: str) -> tuple[int, str] | None:
    match = _MIGRATION_NAME_RE.match(filename)
    if not match:
        return None
    return int(match.group(1)), match.group(2)


def load_migrations(
    directory: Path | None = None,
) -> list[Migration]:
    """加载并排序 migration 脚本。

    默认从包内 ``backend.app.persistence.migrations`` 读取。
    """
    if directory is not None:
        return _load_from_directory(directory)
    return _load_from_package()


def _load_from_directory(directory: Path) -> list[Migration]:
    if not directory.is_dir():
        raise MigrationError(f"migration 目录不存在: {directory}")
    migrations: list[Migration] = []
    for path in sorted(directory.iterdir()):
        if not path.is_file() or path.suffix.lower() != ".sql":
            continue
        parsed = _parse_migration_filename(path.name)
        if parsed is None:
            raise MigrationError(f"非法 migration 文件名: {path.name}")
        version, name = parsed
        migrations.append(
            Migration(
                version=version,
                name=name,
                sql=path.read_text(encoding="utf-8"),
                source=str(path),
            )
        )
    return _validate_unique_versions(migrations)


def _load_from_package() -> list[Migration]:
    package = resources.files("backend.app.persistence.migrations")
    migrations: list[Migration] = []
    for entry in package.iterdir():
        if not entry.name.endswith(".sql"):
            continue
        parsed = _parse_migration_filename(entry.name)
        if parsed is None:
            raise MigrationError(f"非法 migration 文件名: {entry.name}")
        version, name = parsed
        migrations.append(
            Migration(
                version=version,
                name=name,
                sql=entry.read_text(encoding="utf-8"),
                source=f"package:{entry.name}",
            )
        )
    migrations.sort(key=lambda m: m.version)
    return _validate_unique_versions(migrations)


def _validate_unique_versions(migrations: list[Migration]) -> list[Migration]:
    migrations = sorted(migrations, key=lambda m: m.version)
    seen: set[int] = set()
    for item in migrations:
        if item.version in seen:
            raise MigrationError(f"重复的 migration version: {item.version}")
        if item.version < 1:
            raise MigrationError(f"migration version 必须 >= 1: {item.version}")
        seen.add(item.version)
    return migrations


def ensure_migrations_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            applied_at TEXT NOT NULL
        )
        """
    )


def get_applied_versions(conn: sqlite3.Connection) -> set[int]:
    ensure_migrations_table(conn)
    rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
    return {int(row[0]) for row in rows}


def get_schema_version(conn: sqlite3.Connection) -> int:
    applied = get_applied_versions(conn)
    return max(applied) if applied else 0


def apply_migrations(
    conn: sqlite3.Connection,
    *,
    directory: Path | None = None,
) -> list[int]:
    """应用所有未执行的 migration；返回本次新应用的 version 列表。"""
    migrations = load_migrations(directory)
    if not migrations:
        raise MigrationError("未找到任何 migration 脚本")

    ensure_migrations_table(conn)
    applied = get_applied_versions(conn)
    newly: list[int] = []

    for migration in migrations:
        if migration.version in applied:
            continue
        try:
            # executescript 会自行处理脚本内多语句；之后记录 version
            conn.executescript(migration.sql)
            conn.execute(
                "INSERT INTO schema_migrations (version, name, applied_at) "
                "VALUES (?, ?, ?)",
                (migration.version, migration.name, _utc_now_iso()),
            )
            conn.commit()
        except Exception as exc:  # noqa: BLE001
            try:
                conn.rollback()
            except sqlite3.Error:
                pass
            raise MigrationError(
                f"应用 migration v{migration.version} ({migration.name}) 失败: {exc}"
            ) from exc

        newly.append(migration.version)
        applied.add(migration.version)

    return newly
