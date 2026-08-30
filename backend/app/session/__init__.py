"""Session 领域模型（V0.6）。

Phase 2-A：仅序列化与 ID；Repository / SQLite 在后续 Phase。

注意：本包 ``__init__`` 避免急切导入 models，防止与 ``llm.messages`` 循环依赖。
从子模块显式导入：``session.models`` / ``session.ids``。
"""

from backend.app.session.ids import (
    new_agent_run_id,
    new_id,
    new_message_id,
    new_session_id,
    new_step_id,
    new_tool_call_id,
)

__all__ = [
    "new_agent_run_id",
    "new_id",
    "new_message_id",
    "new_session_id",
    "new_step_id",
    "new_tool_call_id",
]
