"""持久化层错误。"""

from __future__ import annotations


class PersistenceError(Exception):
    """SQLite / migration / store 相关错误。"""


class MigrationError(PersistenceError):
    """Schema migration 失败。"""


class RepositoryError(PersistenceError):
    """Repository 操作失败。"""


class NotFoundError(RepositoryError):
    """请求的实体不存在。"""


class ConflictError(RepositoryError):
    """唯一约束或状态冲突。"""
