"""Plan 领域事件构造（无 Rich / 无 CLI）。

事件经 AgentEventSink 扇出，CLI / 未来 Web 共用同一套 event_type。
"""

from __future__ import annotations

from typing import Any

from backend.app.agent.events import AgentEvent
from backend.app.context.models import Plan, PlanStep, PlanStepStatus

PLAN_CREATED = "plan_created"
PLAN_STEP_STARTED = "plan_step_started"
PLAN_STEP_COMPLETED = "plan_step_completed"
PLAN_STEP_FAILED = "plan_step_failed"
PLAN_COMPLETED = "plan_completed"

PLAN_EVENT_TYPES = frozenset(
    {
        PLAN_CREATED,
        PLAN_STEP_STARTED,
        PLAN_STEP_COMPLETED,
        PLAN_STEP_FAILED,
        PLAN_COMPLETED,
    }
)


def step_payload(step: PlanStep) -> dict[str, Any]:
    return {
        "step_id": step.step_id,
        "step_index": step.step_index,
        "title": step.title,
        "status": step.status.value,
        "description": step.description,
    }


def plan_created_event(
    plan: Plan,
    *,
    agent_step: int = 0,
) -> AgentEvent:
    return AgentEvent(
        event_type=PLAN_CREATED,
        step=agent_step,
        metadata={
            "session_id": plan.session_id,
            "agent_run_id": plan.agent_run_id,
            "plan_id": plan.plan_id,
            "goal": plan.goal,
            "status": plan.status.value,
            "steps": [step_payload(s) for s in sorted(plan.steps, key=lambda x: x.step_index)],
        },
    )


def plan_step_event(
    event_type: str,
    plan: Plan,
    step: PlanStep,
    *,
    agent_step: int = 0,
    reason: str | None = None,
) -> AgentEvent:
    meta: dict[str, Any] = {
        "session_id": plan.session_id,
        "agent_run_id": plan.agent_run_id,
        "plan_id": plan.plan_id,
        "step_id": step.step_id,
        "step_index": step.step_index,
        "title": step.title,
        "status": step.status.value,
    }
    if reason:
        meta["reason"] = reason
    return AgentEvent(event_type=event_type, step=agent_step, metadata=meta)


def plan_completed_event(plan: Plan, *, agent_step: int = 0) -> AgentEvent:
    return AgentEvent(
        event_type=PLAN_COMPLETED,
        step=agent_step,
        metadata={
            "session_id": plan.session_id,
            "agent_run_id": plan.agent_run_id,
            "plan_id": plan.plan_id,
            "status": plan.status.value,
            "steps": [step_payload(s) for s in sorted(plan.steps, key=lambda x: x.step_index)],
        },
    )


def event_type_for_step_status(status: PlanStepStatus) -> str | None:
    """状态落到事件类型；PENDING 无独立事件。"""
    if status == PlanStepStatus.IN_PROGRESS:
        return PLAN_STEP_STARTED
    if status == PlanStepStatus.COMPLETED:
        return PLAN_STEP_COMPLETED
    if status in {PlanStepStatus.FAILED, PlanStepStatus.BLOCKED}:
        return PLAN_STEP_FAILED
    if status == PlanStepStatus.SKIPPED:
        # 规格无独立 skipped 事件；用 completed + status=skipped 表达
        return PLAN_STEP_COMPLETED
    return None
