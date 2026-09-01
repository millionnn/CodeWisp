"""
引入session，表示对话的管理对象
稳定领域 ID 生成（与厂商 tool_call id、内存 step 下标解耦）。

格式：``{prefix}_{32-hex}``，例如 ``tc_a1b2...``、``step_...``。
供持久化与未来 Snapshot/Undo 关联；不依赖 SQLite。
"""

from __future__ import annotations

import uuid


#生成带前缀的稳定唯一 ID
def new_id(prefix: str) -> str:
    """生成带前缀的稳定唯一 ID。"""
    p = (prefix or "").strip().rstrip("_")
    if not p:
        raise ValueError("id prefix 不能为空")
    return f"{p}_{uuid.uuid4().hex}"


def new_session_id() -> str:
    return new_id("ses")


def new_message_id() -> str:
    return new_id("msg")


def new_agent_run_id() -> str:
    return new_id("run")


def new_step_id() -> str:
    return new_id("step")


def new_tool_call_id() -> str:
    return new_id("tc")
