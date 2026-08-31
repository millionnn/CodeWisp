"""结构化 Plan JSON 解析。"""

from __future__ import annotations

import json
import re
from typing import Any

from backend.app.context.models import Plan, PlanStep, PlanStepStatus, PlanStatus
from backend.app.persistence._util import utc_now_iso
from backend.app.planning.errors import PlanParseError

_STATUS_MAP = {
    "pending": PlanStepStatus.PENDING,
    "in_progress": PlanStepStatus.IN_PROGRESS,
    "completed": PlanStepStatus.COMPLETED,
    "failed": PlanStepStatus.FAILED,
    "skipped": PlanStepStatus.SKIPPED,
    "blocked": PlanStepStatus.FAILED,  # fallback if BLOCKED missing — patched below
}


def parse_plan_json(
    text: str,
    *,
    session_id: str,
    agent_run_id: str | None = None,
    existing: Plan | None = None,
) -> Plan:
    data = _loads_json_object(text)
    objective = str(data.get("objective") or (existing.goal if existing else "")).strip()
    if not objective:
        raise PlanParseError("plan JSON 缺少 objective")
    raw_steps = data.get("steps")
    if not isinstance(raw_steps, list) or not raw_steps:
        raise PlanParseError("plan JSON 缺少 steps")

    plan = existing or Plan.create(
        session_id=session_id,
        goal=objective,
        agent_run_id=agent_run_id,
        step_titles=[],
    )
    plan.goal = objective
    plan.agent_run_id = agent_run_id or plan.agent_run_id
    plan.status = PlanStatus.IN_PROGRESS
    plan.updated_at = utc_now_iso()

    new_steps: list[PlanStep] = []
    for i, raw in enumerate(raw_steps):
        if not isinstance(raw, dict):
            continue
        title = str(raw.get("title") or raw.get("description") or f"Step {i + 1}").strip()
        desc = str(raw.get("description") or "").strip() or None
        status_raw = str(raw.get("status") or "pending").lower()
        status = _STATUS_MAP.get(status_raw, PlanStepStatus.PENDING)
        # prefer blocked enum if available
        if status_raw == "blocked" and hasattr(PlanStepStatus, "BLOCKED"):
            status = PlanStepStatus.BLOCKED  # type: ignore[attr-defined]
        raw_idx = raw.get("index", i)
        try:
            idx = int(raw_idx)
        except (TypeError, ValueError):
            idx = i
        step = PlanStep.create(
            plan_id=plan.plan_id,
            step_index=idx,
            title=title[:200],
            description=desc,
        )
        step.status = status
        # optional enriched fields on instance
        step.__dict__["relevant_files"] = list(raw.get("relevant_files") or [])
        step.__dict__["verification"] = raw.get("verification")
        step.__dict__["rationale"] = raw.get("rationale")
        step.__dict__["dependencies"] = list(raw.get("dependencies") or [])
        new_steps.append(step)

    if not new_steps:
        raise PlanParseError("plan steps 为空")

    # LLM 常把 index 从 1 开始，或跳号；统一压成 0..n-1
    new_steps.sort(key=lambda s: s.step_index)
    for i, step in enumerate(new_steps):
        step.step_index = i

    # 初始计划：只允许第一步 in_progress，其余 pending（避免伪造已完成/失败）
    if existing is None:
        for i, step in enumerate(new_steps):
            step.status = (
                PlanStepStatus.IN_PROGRESS if i == 0 else PlanStepStatus.PENDING
            )
    elif not any(s.status == PlanStepStatus.IN_PROGRESS for s in new_steps):
        for s in new_steps:
            if s.status == PlanStepStatus.PENDING:
                s.status = PlanStepStatus.IN_PROGRESS
                break
        else:
            new_steps[0].status = PlanStepStatus.IN_PROGRESS

    # Replan 不得把 6 步清单缩成 1 步；保留原 steps，只合并同名/同序号状态
    if existing is not None and existing.steps and len(new_steps) < len(existing.steps):
        by_index = {s.step_index: s for s in new_steps}
        by_title = {s.title.strip(): s for s in new_steps}
        merged: list[PlanStep] = []
        for old in sorted(existing.steps, key=lambda s: s.step_index):
            incoming = by_index.get(old.step_index) or by_title.get(old.title.strip())
            if incoming is None:
                merged.append(old)
                continue
            old.status = incoming.status
            if incoming.description:
                old.description = incoming.description
            merged.append(old)
        if not any(s.status == PlanStepStatus.IN_PROGRESS for s in merged):
            for s in merged:
                if s.status == PlanStepStatus.PENDING:
                    s.status = PlanStepStatus.IN_PROGRESS
                    break
        new_steps = merged
        for i, step in enumerate(new_steps):
            step.step_index = i

    plan.steps = new_steps
    return plan


def _loads_json_object(text: str) -> dict[str, Any]:
    if not text or not text.strip():
        raise PlanParseError("空响应")
    raw = text.strip()
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            raise PlanParseError("无法解析 JSON") from None
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError as exc:
            raise PlanParseError(f"无法解析 JSON: {exc}") from exc
    if not isinstance(data, dict):
        raise PlanParseError("JSON 根必须是 object")
    return data
