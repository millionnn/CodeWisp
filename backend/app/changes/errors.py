"""Workspace Change 错误类型。"""

from __future__ import annotations


class ChangeError(Exception):
    """Snapshot / Diff / Restore 基础错误。"""


class SnapshotNotFoundError(ChangeError):
    """指定 snapshot_id 不存在。"""


class RestoreError(ChangeError):
    """Restore 过程失败（可能已部分应用）。"""


class RevertError(ChangeError):
    """Revert 失败（无 snapshot / 校验失败等）。"""


class RevertDeniedError(RevertError):
    """PermissionHandler 拒绝 Revert。"""
