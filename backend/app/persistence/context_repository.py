"""Task / Plan / Memory / Checkpoint 持久化。"""

from __future__ import annotations

import sqlite3
from typing import Any

from backend.app.context.models import (
    CheckpointTrigger,
    ContextCheckpoint,
    MemoryCategory,
    MemoryItem,
    MemorySourceType,
    Plan,
    PlanStatus,
    PlanStep,
    PlanStepStatus,
    TaskState,
    TaskStatus,
    WorkspaceState,
)
from backend.app.context.priority import ContextPriority
from backend.app.persistence._util import dumps_json, loads_json, utc_now_iso
from backend.app.persistence.errors import NotFoundError
from backend.app.persistence.store import SqliteStore

#存取task、plan、memory、checkpoint，按照文件路径把memory分类

class ContextRepository:
    def __init__(self, store: SqliteStore) -> None:
        self._store = store

    # ── TaskState ──────────────────────────────────────────────

    def upsert_task(self, task: TaskState) -> TaskState:
        task.touch()
        if task.is_active:
            self._store.execute(
                "UPDATE task_states SET is_active=0, updated_at=? WHERE session_id=? AND is_active=1 AND id!=?",
                (utc_now_iso(), task.session_id, task.task_id),
            )
        self._store.execute(
            """
            INSERT INTO task_states (
                id, session_id, goal, status, current_focus,
                completed_items_json, blockers_json, next_actions_json,
                important_decisions_json, workspace_state_json, is_active,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                goal=excluded.goal,
                status=excluded.status,
                current_focus=excluded.current_focus,
                completed_items_json=excluded.completed_items_json,
                blockers_json=excluded.blockers_json,
                next_actions_json=excluded.next_actions_json,
                important_decisions_json=excluded.important_decisions_json,
                workspace_state_json=excluded.workspace_state_json,
                is_active=excluded.is_active,
                updated_at=excluded.updated_at
            """,
            (
                task.task_id,
                task.session_id,
                task.goal,
                task.status.value,
                task.current_focus,
                dumps_json(task.completed_items),
                dumps_json(task.blockers),
                dumps_json(task.next_actions),
                dumps_json(task.important_decisions),
                dumps_json(task.workspace_state.to_dict()),
                1 if task.is_active else 0,
                task.created_at or utc_now_iso(),
                task.updated_at or utc_now_iso(),
            ),
        )
        self._store.commit()
        return task

    def get_active_task(self, session_id: str) -> TaskState | None:
        row = self._store.execute(
            "SELECT * FROM task_states WHERE session_id=? AND is_active=1 ORDER BY updated_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return self._row_to_task(row) if row else None

    def get_task(self, task_id: str) -> TaskState:
        row = self._store.execute(
            "SELECT * FROM task_states WHERE id=?",
            (task_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"TaskState 不存在: {task_id}")
        return self._row_to_task(row)

    def _row_to_task(self, row: sqlite3.Row) -> TaskState:
        ws = loads_json(row["workspace_state_json"], default={}) or {}
        return TaskState(
            task_id=row["id"],
            session_id=row["session_id"],
            goal=row["goal"],
            status=TaskStatus(row["status"]),
            current_focus=row["current_focus"],
            completed_items=list(loads_json(row["completed_items_json"], default=[]) or []),
            blockers=list(loads_json(row["blockers_json"], default=[]) or []),
            next_actions=list(loads_json(row["next_actions_json"], default=[]) or []),
            important_decisions=list(
                loads_json(row["important_decisions_json"], default=[]) or []
            ),
            workspace_state=WorkspaceState.from_dict(ws if isinstance(ws, dict) else {}),
            is_active=bool(row["is_active"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ── Plan ───────────────────────────────────────────────────

    def save_plan(self, plan: Plan) -> Plan:
        plan.updated_at = utc_now_iso()
        self._store.execute(
            """
            INSERT INTO plans (id, session_id, agent_run_id, goal, status, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                agent_run_id=excluded.agent_run_id,
                goal=excluded.goal,
                status=excluded.status,
                updated_at=excluded.updated_at
            """,
            (
                plan.plan_id,
                plan.session_id,
                plan.agent_run_id,
                plan.goal,
                plan.status.value,
                plan.created_at or utc_now_iso(),
                plan.updated_at,
            ),
        )
        self._store.execute("DELETE FROM plan_steps WHERE plan_id=?", (plan.plan_id,))
        for step in plan.steps:
            step.updated_at = plan.updated_at
            self._store.execute(
                """
                INSERT INTO plan_steps (
                    id, plan_id, step_index, title, description, status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    step.step_id,
                    step.plan_id,
                    step.step_index,
                    step.title,
                    step.description,
                    step.status.value,
                    step.created_at or utc_now_iso(),
                    step.updated_at,
                ),
            )
        self._store.commit()
        return plan

    def get_plan(self, plan_id: str) -> Plan:
        row = self._store.execute(
            "SELECT * FROM plans WHERE id=?",
            (plan_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Plan 不存在: {plan_id}")
        return self._plan_from_row(row)

    def get_latest_plan(self, session_id: str) -> Plan | None:
        row = self._store.execute(
            "SELECT * FROM plans WHERE session_id=? ORDER BY updated_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return self._plan_from_row(row) if row else None

    def list_plans(self, session_id: str) -> list[Plan]:
        rows = self._store.execute(
            "SELECT * FROM plans WHERE session_id=? ORDER BY updated_at DESC",
            (session_id,),
        ).fetchall()
        return [self._plan_from_row(r) for r in rows]

    def _plan_from_row(self, row: sqlite3.Row) -> Plan:
        steps_rows = self._store.execute(
            "SELECT * FROM plan_steps WHERE plan_id=? ORDER BY step_index ASC",
            (row["id"],),
        ).fetchall()
        steps = [
            PlanStep(
                step_id=s["id"],
                plan_id=s["plan_id"],
                step_index=s["step_index"],
                title=s["title"],
                description=s["description"],
                status=PlanStepStatus(s["status"]),
                created_at=s["created_at"],
                updated_at=s["updated_at"],
            )
            for s in steps_rows
        ]
        return Plan(
            plan_id=row["id"],
            session_id=row["session_id"],
            goal=row["goal"],
            status=PlanStatus(row["status"]),
            agent_run_id=row["agent_run_id"],
            steps=steps,
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ── Memory ─────────────────────────────────────────────────

    def save_memory(self, item: MemoryItem) -> MemoryItem:
        item.updated_at = utc_now_iso()
        self._store.execute(
            """
            INSERT INTO memories (
                id, session_id, category, content, source_type, source_id,
                file_path, line_start, line_end, priority, invalidated,
                created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                category=excluded.category,
                content=excluded.content,
                source_type=excluded.source_type,
                source_id=excluded.source_id,
                file_path=excluded.file_path,
                line_start=excluded.line_start,
                line_end=excluded.line_end,
                priority=excluded.priority,
                invalidated=excluded.invalidated,
                updated_at=excluded.updated_at
            """,
            (
                item.memory_id,
                item.session_id,
                item.category.value,
                item.content,
                item.source_type.value,
                item.source_id,
                item.file_path,
                item.line_start,
                item.line_end,
                int(item.priority),
                1 if item.invalidated else 0,
                item.created_at or utc_now_iso(),
                item.updated_at,
            ),
        )
        self._store.commit()
        return item

    def list_memories(
        self,
        session_id: str,
        *,
        include_invalidated: bool = False,
        limit: int = 50,
    ) -> list[MemoryItem]:
        if include_invalidated:
            rows = self._store.execute(
                "SELECT * FROM memories WHERE session_id=? ORDER BY updated_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        else:
            rows = self._store.execute(
                "SELECT * FROM memories WHERE session_id=? AND invalidated=0 "
                "ORDER BY priority ASC, updated_at DESC LIMIT ?",
                (session_id, limit),
            ).fetchall()
        return [self._row_to_memory(r) for r in rows]

    def invalidate_memories_for_paths(self, session_id: str, paths: list[str]) -> int:
        if not paths:
            return 0
        count = 0
        now = utc_now_iso()
        for path in paths:
            cur = self._store.execute(
                "UPDATE memories SET invalidated=1, updated_at=? "
                "WHERE session_id=? AND file_path=? AND invalidated=0",
                (now, session_id, path),
            )
            count += cur.rowcount if cur.rowcount and cur.rowcount > 0 else 0
        self._store.commit()
        return count

    def invalidate_workspace_facts(self, session_id: str) -> int:
        """失效可能依赖工作区内容的 memory（architecture / important_fact + file_path）。"""
        now = utc_now_iso()
        cur = self._store.execute(
            "UPDATE memories SET invalidated=1, updated_at=? "
            "WHERE session_id=? AND invalidated=0 AND ("
            "  file_path IS NOT NULL OR category IN ('architecture', 'important_fact')"
            ")",
            (now, session_id),
        )
        self._store.commit()
        return int(cur.rowcount or 0)

    def _row_to_memory(self, row: sqlite3.Row) -> MemoryItem:
        return MemoryItem(
            memory_id=row["id"],
            session_id=row["session_id"],
            category=MemoryCategory(row["category"]),
            content=row["content"],
            source_type=MemorySourceType(row["source_type"]),
            source_id=row["source_id"],
            file_path=row["file_path"],
            line_start=row["line_start"],
            line_end=row["line_end"],
            priority=ContextPriority(int(row["priority"])),
            invalidated=bool(row["invalidated"]),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    # ── Checkpoint ─────────────────────────────────────────────

    def save_checkpoint(self, ckpt: ContextCheckpoint) -> ContextCheckpoint:
        self._store.execute(
            """
            INSERT INTO context_checkpoints (
                id, session_id, trigger, summary_json, retained_message_boundary,
                model_id, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                ckpt.checkpoint_id,
                ckpt.session_id,
                ckpt.trigger.value,
                dumps_json(ckpt.summary),
                ckpt.retained_message_boundary,
                ckpt.model_id,
                ckpt.created_at or utc_now_iso(),
            ),
        )
        self._store.commit()
        return ckpt

    def get_latest_checkpoint(self, session_id: str) -> ContextCheckpoint | None:
        row = self._store.execute(
            "SELECT * FROM context_checkpoints WHERE session_id=? "
            "ORDER BY created_at DESC LIMIT 1",
            (session_id,),
        ).fetchone()
        return self._row_to_checkpoint(row) if row else None

    def list_checkpoints(self, session_id: str, *, limit: int = 20) -> list[ContextCheckpoint]:
        rows = self._store.execute(
            "SELECT * FROM context_checkpoints WHERE session_id=? "
            "ORDER BY created_at DESC LIMIT ?",
            (session_id, limit),
        ).fetchall()
        return [self._row_to_checkpoint(r) for r in rows]

    def _row_to_checkpoint(self, row: sqlite3.Row) -> ContextCheckpoint:
        summary = loads_json(row["summary_json"], default={}) or {}
        return ContextCheckpoint(
            checkpoint_id=row["id"],
            session_id=row["session_id"],
            trigger=CheckpointTrigger(row["trigger"]),
            summary=summary if isinstance(summary, dict) else {},
            retained_message_boundary=row["retained_message_boundary"],
            model_id=row["model_id"],
            created_at=row["created_at"],
        )
