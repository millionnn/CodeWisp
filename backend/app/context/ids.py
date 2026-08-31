"""Context 域稳定 ID。"""

from __future__ import annotations

from backend.app.session.ids import new_id


def new_task_id() -> str:
    return new_id("task")


def new_plan_id() -> str:
    return new_id("plan")


def new_plan_step_id() -> str:
    return new_id("ps")


def new_memory_id() -> str:
    return new_id("mem")


def new_checkpoint_id() -> str:
    return new_id("ckpt")
