"""Snapshot 稳定 ID。"""

from __future__ import annotations

from backend.app.session.ids import new_id

#生成新的 snapshot id
def new_snapshot_id() -> str:
    return new_id("snap")


def new_file_change_id() -> str:
    return new_id("chg")
