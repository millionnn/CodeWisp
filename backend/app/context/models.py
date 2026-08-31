"""V1.0 Context 领域模型（结构化状态，非巨型 summary）。"""

#定义各个数据结构，task、plan、memory、checkpoint

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.app.context.ids import (
    new_checkpoint_id,
    new_memory_id,
    new_plan_id,
    new_plan_step_id,
    new_task_id,
)
from backend.app.context.priority import ContextPriority
from backend.app.persistence._util import utc_now_iso


class TaskStatus(str, Enum):
    ACTIVE = "active"
    BLOCKED = "blocked"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class PlanStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class PlanStepStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"
    BLOCKED = "blocked"


class MemoryCategory(str, Enum):
    DECISION = "decision"
    ARCHITECTURE = "architecture"
    CONSTRAINT = "constraint"
    IMPORTANT_FACT = "important_fact"
    WORKFLOW = "workflow"


class MemorySourceType(str, Enum):
    USER = "user"
    TOOL_OBSERVATION = "tool_observation"
    AGENT = "agent"
    PROJECT_RULE = "project_rule"


class CheckpointTrigger(str, Enum):
    AUTOMATIC = "automatic"
    MANUAL = "manual"
    OVERFLOW_RECOVERY = "overflow_recovery"


def _str_list(data: Any) -> list[str]:
    if data is None:
        return []
    if isinstance(data, list):
        return [str(x) for x in data]
    raise ValueError("期望 list[str]")


@dataclass
class WorkspaceState:
    """工作区元数据（metadata first，不把整个仓库塞进 prompt）。"""

    important_files: list[str] = field(default_factory=list)
    active_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)
    recent_changes: list[str] = field(default_factory=list)
    recent_tests: list[str] = field(default_factory=list)
    test_results: list[str] = field(default_factory=list)
    workspace_structure: list[str] = field(default_factory=list)
    stale: bool = False

    def mark_modified(self, path: str) -> None:
        if path not in self.modified_files:
            self.modified_files.append(path)
        if path not in self.active_files:
            self.active_files.append(path)
        note = f"modified:{path}"
        if note not in self.recent_changes:
            self.recent_changes.append(note)
            self.recent_changes = self.recent_changes[-20:]

    def record_test(self, summary: str, *, failed: bool) -> None:
        self.recent_tests.append(summary)
        self.recent_tests = self.recent_tests[-10:]
        self.test_results.append(("FAIL: " if failed else "PASS: ") + summary)
        self.test_results = self.test_results[-10:]

    def invalidate(self, *, paths: list[str] | None = None) -> None:
        self.stale = True
        if paths:
            for p in paths:
                if p in self.modified_files:
                    self.modified_files.remove(p)
                note = f"reverted:{p}"
                self.recent_changes.append(note)
            self.recent_changes = self.recent_changes[-20:]
        else:
            self.modified_files.clear()
            self.recent_changes.append("workspace_invalidated")
            self.recent_changes = self.recent_changes[-20:]
        self.test_results.append("INVALIDATED after revert — re-run tests before trusting results")
        self.test_results = self.test_results[-10:]

    def to_dict(self) -> dict[str, Any]:
        return {
            "important_files": list(self.important_files),
            "active_files": list(self.active_files),
            "modified_files": list(self.modified_files),
            "recent_changes": list(self.recent_changes),
            "recent_tests": list(self.recent_tests),
            "test_results": list(self.test_results),
            "workspace_structure": list(self.workspace_structure),
            "stale": self.stale,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> WorkspaceState:
        if not data:
            return cls()
        return cls(
            important_files=_str_list(data.get("important_files")),
            active_files=_str_list(data.get("active_files")),
            modified_files=_str_list(data.get("modified_files")),
            recent_changes=_str_list(data.get("recent_changes")),
            recent_tests=_str_list(data.get("recent_tests")),
            test_results=_str_list(data.get("test_results")),
            workspace_structure=_str_list(data.get("workspace_structure")),
            stale=bool(data.get("stale", False)),
        )

    def render(self) -> str:
        lines = ["## Workspace State"]
        if self.stale:
            lines.append("WARNING: workspace context is STALE after revert; re-read files before acting.")
        if self.modified_files:
            lines.append("Modified files: " + ", ".join(self.modified_files[-15:]))
        if self.active_files:
            lines.append("Active files: " + ", ".join(self.active_files[-10:]))
        if self.recent_changes:
            lines.append("Recent changes:")
            for c in self.recent_changes[-8:]:
                lines.append(f"  - {c}")
        if self.test_results:
            lines.append("Recent test results:")
            for t in self.test_results[-5:]:
                lines.append(f"  - {t}")
        if self.workspace_structure:
            lines.append("Structure hints: " + ", ".join(self.workspace_structure[:12]))
        if len(lines) == 1:
            lines.append("(no workspace metadata yet)")
        return "\n".join(lines)


@dataclass
class TaskState:
    task_id: str
    session_id: str
    goal: str
    status: TaskStatus = TaskStatus.ACTIVE
    current_focus: str | None = None
    completed_items: list[str] = field(default_factory=list)
    blockers: list[str] = field(default_factory=list)
    next_actions: list[str] = field(default_factory=list)
    important_decisions: list[str] = field(default_factory=list)
    workspace_state: WorkspaceState = field(default_factory=WorkspaceState)
    is_active: bool = True
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def create(cls, *, session_id: str, goal: str) -> TaskState:
        now = utc_now_iso()
        return cls(
            task_id=new_task_id(),
            session_id=session_id,
            goal=goal.strip(),
            created_at=now,
            updated_at=now,
        )

    def touch(self) -> None:
        self.updated_at = utc_now_iso()

    def render(self) -> str:
        lines = [
            "## Task State",
            f"Goal: {self.goal}",
            f"Status: {self.status.value}",
        ]
        if self.current_focus:
            lines.append(f"Current: {self.current_focus}")
        if self.completed_items:
            lines.append("Completed:")
            for item in self.completed_items[-12:]:
                lines.append(f"  - {item}")
        if self.blockers:
            lines.append("Blockers:")
            for b in self.blockers[-8:]:
                lines.append(f"  - {b}")
        if self.next_actions:
            lines.append("Next:")
            for a in self.next_actions[-8:]:
                lines.append(f"  - {a}")
        if self.important_decisions:
            lines.append("Important decisions:")
            for d in self.important_decisions[-8:]:
                lines.append(f"  - {d}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "task_id": self.task_id,
            "session_id": self.session_id,
            "goal": self.goal,
            "status": self.status.value,
            "current_focus": self.current_focus,
            "completed_items": list(self.completed_items),
            "blockers": list(self.blockers),
            "next_actions": list(self.next_actions),
            "important_decisions": list(self.important_decisions),
            "workspace_state": self.workspace_state.to_dict(),
            "is_active": self.is_active,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TaskState:
        status_raw = data.get("status", TaskStatus.ACTIVE.value)
        return cls(
            task_id=str(data["task_id"]),
            session_id=str(data["session_id"]),
            goal=str(data["goal"]),
            status=TaskStatus(status_raw),
            current_focus=data.get("current_focus"),
            completed_items=_str_list(data.get("completed_items")),
            blockers=_str_list(data.get("blockers")),
            next_actions=_str_list(data.get("next_actions")),
            important_decisions=_str_list(data.get("important_decisions")),
            workspace_state=WorkspaceState.from_dict(data.get("workspace_state")),
            is_active=bool(data.get("is_active", True)),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class PlanStep:
    step_id: str
    plan_id: str
    step_index: int
    title: str
    description: str | None = None
    status: PlanStepStatus = PlanStepStatus.PENDING
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def create(
        cls,
        *,
        plan_id: str,
        step_index: int,
        title: str,
        description: str | None = None,
    ) -> PlanStep:
        now = utc_now_iso()
        return cls(
            step_id=new_plan_step_id(),
            plan_id=plan_id,
            step_index=step_index,
            title=title.strip(),
            description=(description or "").strip() or None,
            created_at=now,
            updated_at=now,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "plan_id": self.plan_id,
            "step_index": self.step_index,
            "title": self.title,
            "description": self.description,
            "status": self.status.value,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PlanStep:
        return cls(
            step_id=str(data["step_id"]),
            plan_id=str(data["plan_id"]),
            step_index=int(data["step_index"]),
            title=str(data["title"]),
            description=data.get("description"),
            status=PlanStepStatus(data.get("status", PlanStepStatus.PENDING.value)),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class Plan:
    plan_id: str
    session_id: str
    goal: str
    status: PlanStatus = PlanStatus.PENDING
    agent_run_id: str | None = None
    steps: list[PlanStep] = field(default_factory=list)
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        goal: str,
        agent_run_id: str | None = None,
        step_titles: list[str] | None = None,
    ) -> Plan:
        now = utc_now_iso()
        plan = cls(
            plan_id=new_plan_id(),
            session_id=session_id,
            goal=goal.strip(),
            agent_run_id=agent_run_id,
            status=PlanStatus.IN_PROGRESS,
            created_at=now,
            updated_at=now,
        )
        for i, title in enumerate(step_titles or []):
            plan.steps.append(
                PlanStep.create(plan_id=plan.plan_id, step_index=i, title=title)
            )
        if plan.steps:
            plan.steps[0].status = PlanStepStatus.IN_PROGRESS
        return plan

    def render(self) -> str:
        lines = [
            "## Plan",
            f"Goal: {self.goal}",
            f"Status: {self.status.value}",
        ]
        for step in sorted(self.steps, key=lambda s: s.step_index):
            mark = {
                PlanStepStatus.COMPLETED: "[x]",
                PlanStepStatus.IN_PROGRESS: "[>]",
                PlanStepStatus.FAILED: "[!]",
                PlanStepStatus.BLOCKED: "[#]",
                PlanStepStatus.SKIPPED: "[-]",
                PlanStepStatus.PENDING: "[ ]",
            }.get(step.status, "[ ]")
            lines.append(f"  {mark} {step.step_index + 1}. {step.title}")
            if step.description:
                lines.append(f"       {step.description}")
            rationale = getattr(step, "rationale", None)
            if rationale:
                lines.append(f"       why: {rationale}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "plan_id": self.plan_id,
            "session_id": self.session_id,
            "agent_run_id": self.agent_run_id,
            "goal": self.goal,
            "status": self.status.value,
            "steps": [s.to_dict() for s in self.steps],
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Plan:
        steps_raw = data.get("steps") or []
        return cls(
            plan_id=str(data["plan_id"]),
            session_id=str(data["session_id"]),
            goal=str(data["goal"]),
            status=PlanStatus(data.get("status", PlanStatus.PENDING.value)),
            agent_run_id=data.get("agent_run_id"),
            steps=[PlanStep.from_dict(s) for s in steps_raw],
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class MemoryItem:
    memory_id: str
    session_id: str
    category: MemoryCategory
    content: str
    source_type: MemorySourceType
    source_id: str | None = None
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    priority: ContextPriority = ContextPriority.P1
    invalidated: bool = False
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        category: MemoryCategory,
        content: str,
        source_type: MemorySourceType,
        source_id: str | None = None,
        file_path: str | None = None,
        line_start: int | None = None,
        line_end: int | None = None,
        priority: ContextPriority = ContextPriority.P1,
    ) -> MemoryItem:
        now = utc_now_iso()
        return cls(
            memory_id=new_memory_id(),
            session_id=session_id,
            category=category,
            content=content.strip(),
            source_type=source_type,
            source_id=source_id,
            file_path=file_path,
            line_start=line_start,
            line_end=line_end,
            priority=priority,
            created_at=now,
            updated_at=now,
        )

    def render_line(self) -> str:
        prov = f"source={self.source_type.value}"
        if self.source_id:
            prov += f":{self.source_id}"
        loc = ""
        if self.file_path:
            loc = f" @ {self.file_path}"
            if self.line_start is not None:
                loc += f":{self.line_start}"
                if self.line_end is not None:
                    loc += f"-{self.line_end}"
        flag = " [INVALIDATED]" if self.invalidated else ""
        return f"- [{self.category.value}] {self.content} ({prov}{loc}){flag}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "memory_id": self.memory_id,
            "session_id": self.session_id,
            "category": self.category.value,
            "content": self.content,
            "source_type": self.source_type.value,
            "source_id": self.source_id,
            "file_path": self.file_path,
            "line_start": self.line_start,
            "line_end": self.line_end,
            "priority": int(self.priority),
            "invalidated": self.invalidated,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> MemoryItem:
        return cls(
            memory_id=str(data["memory_id"]),
            session_id=str(data["session_id"]),
            category=MemoryCategory(data["category"]),
            content=str(data["content"]),
            source_type=MemorySourceType(data["source_type"]),
            source_id=data.get("source_id"),
            file_path=data.get("file_path"),
            line_start=data.get("line_start"),
            line_end=data.get("line_end"),
            priority=ContextPriority(int(data.get("priority", 1))),
            invalidated=bool(data.get("invalidated", False)),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


@dataclass
class ContextCheckpoint:
    checkpoint_id: str
    session_id: str
    trigger: CheckpointTrigger
    summary: dict[str, Any]
    retained_message_boundary: int | None = None
    model_id: str | None = None
    created_at: str | None = None

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        trigger: CheckpointTrigger,
        summary: dict[str, Any],
        retained_message_boundary: int | None = None,
        model_id: str | None = None,
    ) -> ContextCheckpoint:
        return cls(
            checkpoint_id=new_checkpoint_id(),
            session_id=session_id,
            trigger=trigger,
            summary=dict(summary),
            retained_message_boundary=retained_message_boundary,
            model_id=model_id,
            created_at=utc_now_iso(),
        )

    def render(self) -> str:
        s = self.summary
        lines = [
            "## Context Checkpoint",
            f"Trigger: {self.trigger.value}",
            f"Objective: {s.get('objective', '')}",
            f"Status: {s.get('current_status', '')}",
        ]
        for key, label in (
            ("completed_work", "Completed"),
            ("active_work", "Active"),
            ("blockers", "Blockers"),
            ("important_decisions", "Decisions"),
            ("important_files", "Files"),
            ("recent_test_results", "Tests"),
            ("next_actions", "Next"),
        ):
            items = s.get(key) or []
            if isinstance(items, list) and items:
                lines.append(f"{label}:")
                for item in items[:12]:
                    lines.append(f"  - {item}")
            elif isinstance(items, str) and items:
                lines.append(f"{label}: {items}")
        return "\n".join(lines)

    def to_dict(self) -> dict[str, Any]:
        return {
            "checkpoint_id": self.checkpoint_id,
            "session_id": self.session_id,
            "trigger": self.trigger.value,
            "summary": dict(self.summary),
            "retained_message_boundary": self.retained_message_boundary,
            "model_id": self.model_id,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ContextCheckpoint:
        return cls(
            checkpoint_id=str(data["checkpoint_id"]),
            session_id=str(data["session_id"]),
            trigger=CheckpointTrigger(data["trigger"]),
            summary=dict(data.get("summary") or {}),
            retained_message_boundary=data.get("retained_message_boundary"),
            model_id=data.get("model_id"),
            created_at=data.get("created_at"),
        )


@dataclass
class ContextSectionUsage:
    """装配后各层 token 用量（用于 /context 诊断）。"""

    name: str
    tokens: int
    priority: ContextPriority

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "tokens": self.tokens,
            "priority": int(self.priority),
        }


@dataclass
class ContextStatus:
    budget: dict[str, Any]
    sections: list[ContextSectionUsage]
    total_tokens: int
    compaction: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "budget": dict(self.budget),
            "sections": [s.to_dict() for s in self.sections],
            "total_tokens": self.total_tokens,
            "compaction": dict(self.compaction),
        }
