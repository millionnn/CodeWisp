"""持久化路径约定。"""

from __future__ import annotations

from pathlib import Path


def default_db_path() -> Path:
    """默认 SQLite 路径：``~/.codewisp/codewisp.db``。"""
    return Path.home() / ".codewisp" / "codewisp.db"
