"""LLM-driven Planner（非第二套 AgentLoop；不改 Workspace）。"""

from __future__ import annotations

from backend.app.context.models import Plan, PlanStatus, PlanStep, PlanStepStatus
from backend.app.llm.client import LLMClient
from backend.app.llm.messages import Conversation
from backend.app.persistence.context_repository import ContextRepository
from backend.app.planning.errors import PlanParseError, PlanningError
from backend.app.planning.parser import parse_plan_json
from backend.app.planning.prompts import (
    PLAN_SYSTEM,
    REPLAN_SYSTEM,
    build_plan_user_prompt,
    build_replan_user_prompt,
)


class PlannerService:
    def __init__(
        self,
        *,
        llm: LLMClient | None = None,
        repository: ContextRepository | None = None,
    ) -> None:
        self._llm = llm
        self._repo = repository

    def set_llm(self, llm: LLMClient | None) -> None:
        self._llm = llm

    def create_initial_plan(
        self,
        *,
        session_id: str,
        goal: str,
        agent_run_id: str | None = None,
        project_rules: str = "",
        retrieved: str = "",
        memories: str = "",
    ) -> Plan:
        if self._llm is None:
            return self._heuristic_plan(session_id, goal, agent_run_id)
        try:
            conv = Conversation()
            conv.add_system(PLAN_SYSTEM)
            conv.add_user(
                build_plan_user_prompt(
                    goal=goal,
                    project_rules=project_rules,
                    retrieved=retrieved,
                    memories=memories,
                )
            )
            resp = self._llm.chat(conv, tools=None)
            plan = parse_plan_json(
                resp.text,
                session_id=session_id,
                agent_run_id=agent_run_id,
            )
        except (PlanParseError, PlanningError, Exception):
            plan = self._heuristic_plan(session_id, goal, agent_run_id)
        return self._save(plan)

    def replan(
        self,
        plan: Plan,
        *,
        observation: str,
        memories: str = "",
        retrieved: str = "",
    ) -> Plan:
        if self._llm is None:
            return self._heuristic_replan(plan, observation)
        try:
            conv = Conversation()
            conv.add_system(REPLAN_SYSTEM)
            conv.add_user(
                build_replan_user_prompt(
                    goal=plan.goal,
                    current_plan_json=_plan_to_compact_json(plan),
                    observation=observation,
                    memories=memories,
                    retrieved=retrieved,
                )
            )
            resp = self._llm.chat(conv, tools=None)
            updated = parse_plan_json(
                resp.text,
                session_id=plan.session_id,
                agent_run_id=plan.agent_run_id,
                existing=plan,
            )
        except (PlanParseError, PlanningError, Exception):
            updated = self._heuristic_replan(plan, observation)
        return self._save(updated)

    def refresh_plan(
        self,
        *,
        session_id: str,
        goal: str | None = None,
        project_rules: str = "",
        retrieved: str = "",
        memories: str = "",
    ) -> Plan:
        existing = self._repo.get_latest_plan(session_id) if self._repo else None
        g = (goal or (existing.goal if existing else "")).strip()
        if not g:
            raise PlanningError("无 goal，无法 refresh plan")
        return self.create_initial_plan(
            session_id=session_id,
            goal=g,
            agent_run_id=existing.agent_run_id if existing else None,
            project_rules=project_rules,
            retrieved=retrieved,
            memories=memories,
        )

    def _save(self, plan: Plan) -> Plan:
        if self._repo is not None:
            return self._repo.save_plan(plan)
        return plan

    def _heuristic_plan(
        self,
        session_id: str,
        goal: str,
        agent_run_id: str | None,
    ) -> Plan:
        g = goal.lower()
        if any(k in g for k in ("重构", "refactor")):
            titles = [
                "阅读现有结构与项目规则",
                "制定重构边界",
                "分步修改并保持 API 兼容",
                "运行测试套件",
            ]
        elif any(k in g for k in ("缓存", "cache")):
            titles = [
                "检索既有缓存抽象与约定",
                "定位目标服务",
                "复用现有缓存客户端接入",
                "补充/更新测试并验证",
            ]
        else:
            titles = [
                "探索相关代码与项目规则",
                "定位问题根因",
                "实施代码修改",
                "运行验证并修复失败",
            ]
        return Plan.create(
            session_id=session_id,
            goal=goal,
            agent_run_id=agent_run_id,
            step_titles=titles,
        )

    def _heuristic_replan(self, plan: Plan, observation: str) -> Plan:
        obs = observation.lower()
        # 已存在 / already / reuse → skip current in_progress if looks exploratory
        skip_signals = ("already", "已存在", "already exists", "reuse", "found existing")
        if any(s in obs for s in skip_signals):
            for step in plan.steps:
                if step.status == PlanStepStatus.IN_PROGRESS:
                    title_l = step.title.lower()
                    if any(k in title_l for k in ("添加", "add", "implement", "实现", "jwt")):
                        step.status = PlanStepStatus.SKIPPED
                        step.__dict__["rationale"] = "Observation indicates work already exists"
                        for nxt in sorted(plan.steps, key=lambda s: s.step_index):
                            if nxt.status == PlanStepStatus.PENDING:
                                nxt.status = PlanStepStatus.IN_PROGRESS
                                break
                        break
        if "failed" in obs or "error" in obs or "失败" in obs:
            for step in plan.steps:
                if step.status == PlanStepStatus.IN_PROGRESS:
                    step.status = PlanStepStatus.BLOCKED
                    break
        if all(
            s.status in {PlanStepStatus.COMPLETED, PlanStepStatus.SKIPPED}
            for s in plan.steps
        ):
            plan.status = PlanStatus.COMPLETED
        return plan


def _plan_to_compact_json(plan: Plan) -> str:
    import json

    steps = []
    for s in plan.steps:
        steps.append(
            {
                "index": s.step_index,
                "title": s.title,
                "description": s.description,
                "status": s.status.value,
                "relevant_files": list(getattr(s, "relevant_files", []) or []),
                "verification": getattr(s, "verification", None),
                "rationale": getattr(s, "rationale", None),
            }
        )
    return json.dumps(
        {"objective": plan.goal, "status": plan.status.value, "steps": steps},
        ensure_ascii=False,
    )
