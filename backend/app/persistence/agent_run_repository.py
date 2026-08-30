"""AgentRun / AgentStep / ToolCall 持久化 Repository。"""
from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from typing import Any

from backend.app.llm.response import ToolCall
from backend.app.persistence._util import dumps_json, loads_json, utc_now_iso
from backend.app.persistence.errors import ConflictError, NotFoundError, RepositoryError
from backend.app.persistence.store import SqliteStore
from backend.app.session.models import AgentRun, AgentStep
from backend.app.tools.result import ToolResult

#对于一次工具调用的持久化
@dataclass(frozen=True)
class PersistedToolCall:
    """tool_calls 表对应的领域记录（含 observation / result）。"""

    tool_call_id: str
    session_id: str
    agent_run_id: str
    step_id: str
    tool_name: str
    arguments: dict[str, Any]
    arguments_raw: str | None = None
    parse_error: str | None = None
    result: ToolResult | None = None
    created_at: str | None = None

    def to_tool_call(self) -> ToolCall:
        return ToolCall(
            id=self.tool_call_id,
            name=self.tool_name,
            arguments=dict(self.arguments),
            arguments_raw=self.arguments_raw,
            parse_error=self.parse_error,
        ).with_stable_id()

#对于一次agent工作的持久化过程
class AgentRunRepository:
    def __init__(self, store: SqliteStore) -> None:
        self._store = store

#确保session存在
    def _ensure_session(self, session_id: str) -> None:
        row = self._store.execute(
            "SELECT 1 FROM sessions WHERE id = ?",
            (session_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"Session 不存在: {session_id}")

#创建一个agent工作过程
    def create_run(self, run: AgentRun) -> AgentRun:
        self._ensure_session(run.session_id)
        created = run
        if created.created_at is None:
            created = AgentRun(
                agent_run_id=run.agent_run_id,
                session_id=run.session_id,
                provider_id=run.provider_id,
                model_id=run.model_id,
                status=run.status,
                termination_reason=run.termination_reason,
                max_steps=run.max_steps,
                final_answer=run.final_answer,
                error=run.error,
                created_at=utc_now_iso(),
                completed_at=run.completed_at,
            )
        try:
            self._store.execute(
                """
                INSERT INTO agent_runs (
                    id, session_id, provider_id, model_id, status,
                    termination_reason, max_steps, final_answer, error,
                    created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created.agent_run_id,
                    created.session_id,
                    created.provider_id,
                    created.model_id,
                    created.status,
                    created.termination_reason,
                    created.max_steps,
                    created.final_answer,
                    created.error,
                    created.created_at,
                    created.completed_at,
                ),
            )
            self._store.commit()
        except sqlite3.IntegrityError as exc:
            raise ConflictError(f"AgentRun 已存在: {created.agent_run_id}") from exc
        except sqlite3.Error as exc:
            raise RepositoryError(f"创建 AgentRun 失败: {exc}") from exc
        return created

#获取一个agent工作过程
    def get_run(self, agent_run_id: str) -> AgentRun:
        row = self._store.execute(
            "SELECT * FROM agent_runs WHERE id = ?",
            (agent_run_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"AgentRun 不存在: {agent_run_id}")
        return _row_to_run(row)

#获取多个agent工作过程
    def list_runs(self, session_id: str) -> list[AgentRun]:
        self._ensure_session(session_id)
        rows = self._store.execute(
            """
            SELECT * FROM agent_runs
            WHERE session_id = ?
            ORDER BY rowid ASC
            """,
            (session_id,),
        ).fetchall()
        return [_row_to_run(row) for row in rows]

#完成一次agent的一次工作
    def complete_run(
        self,
        agent_run_id: str,
        *,
        status: str,
        termination_reason: str | None = None,
        final_answer: str | None = None,
        error: str | None = None,
        completed_at: str | None = None,
    ) -> AgentRun:
        current = self.get_run(agent_run_id)
        updated = AgentRun(
            agent_run_id=current.agent_run_id,
            session_id=current.session_id,
            provider_id=current.provider_id,
            model_id=current.model_id,
            status=status,
            termination_reason=termination_reason,
            max_steps=current.max_steps,
            final_answer=final_answer,
            error=error,
            created_at=current.created_at,
            completed_at=completed_at or utc_now_iso(),
        )
        try:
            self._store.execute(
                """
                UPDATE agent_runs SET
                    status = ?, termination_reason = ?, final_answer = ?,
                    error = ?, completed_at = ?
                WHERE id = ?
                """,
                (
                    updated.status,
                    updated.termination_reason,
                    updated.final_answer,
                    updated.error,
                    updated.completed_at,
                    agent_run_id,
                ),
            )
            self._store.commit()
        except sqlite3.Error as exc:
            raise RepositoryError(f"完成 AgentRun 失败: {exc}") from exc
        return updated

#添加一个agent工作步骤
    def add_step(self, step: AgentStep) -> AgentStep:
        self._ensure_session(step.session_id)
        # run 必须存在
        self.get_run(step.agent_run_id)
        created = step
        if created.created_at is None:
            created = AgentStep(
                step_id=step.step_id,
                agent_run_id=step.agent_run_id,
                session_id=step.session_id,
                step_index=step.step_index,
                status=step.status,
                created_at=utc_now_iso(),
                completed_at=step.completed_at,
            )
        try:
            self._store.execute(
                """
                INSERT INTO agent_steps (
                    id, agent_run_id, session_id, step_index, status,
                    created_at, completed_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    created.step_id,
                    created.agent_run_id,
                    created.session_id,
                    created.step_index,
                    created.status,
                    created.created_at,
                    created.completed_at,
                ),
            )
            self._store.commit()
        except sqlite3.IntegrityError as exc:
            raise ConflictError(
                f"AgentStep 冲突: {created.step_id} / index={created.step_index}"
            ) from exc
        except sqlite3.Error as exc:
            raise RepositoryError(f"创建 AgentStep 失败: {exc}") from exc
        return created

#获取一个agent工作步骤
    def get_step(self, step_id: str) -> AgentStep:
        row = self._store.execute(
            "SELECT * FROM agent_steps WHERE id = ?",
            (step_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"AgentStep 不存在: {step_id}")
        return _row_to_step(row)

#获取一次agent工作中的多个agent工作步骤
    def list_steps(self, agent_run_id: str) -> list[AgentStep]:
        self.get_run(agent_run_id)
        rows = self._store.execute(
            """
            SELECT * FROM agent_steps
            WHERE agent_run_id = ?
            ORDER BY step_index ASC
            """,
            (agent_run_id,),
        ).fetchall()
        return [_row_to_step(row) for row in rows]

#完成一个agent工作步骤
    def complete_step(
        self,
        step_id: str,
        *,
        status: str = "completed",
        completed_at: str | None = None,
    ) -> AgentStep:
        current = self.get_step(step_id)
        updated = AgentStep(
            step_id=current.step_id,
            agent_run_id=current.agent_run_id,
            session_id=current.session_id,
            step_index=current.step_index,
            status=status,
            created_at=current.created_at,
            completed_at=completed_at or utc_now_iso(),
        )
        try:
            self._store.execute(
                """
                UPDATE agent_steps SET status = ?, completed_at = ?
                WHERE id = ?
                """,
                (updated.status, updated.completed_at, step_id),
            )
            self._store.commit()
        except sqlite3.Error as exc:
            raise RepositoryError(f"完成 AgentStep 失败: {exc}") from exc
        return updated

#添加一个工具调用
    def add_tool_call(
        self,
        *,
        session_id: str,
        agent_run_id: str,
        step_id: str,
        tool_call: ToolCall,
        result: ToolResult | None = None,
        created_at: str | None = None,
    ) -> PersistedToolCall:
        self._ensure_session(session_id)
        self.get_run(agent_run_id)
        self.get_step(step_id)
        stable = tool_call.with_stable_id()
        ts = created_at or utc_now_iso()
        result_json = dumps_json(result.to_dict()) if result is not None else None
        try:
            self._store.execute(
                """
                INSERT INTO tool_calls (
                    id, session_id, agent_run_id, step_id, tool_name,
                    arguments_json, arguments_raw, parse_error, result_json, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    stable.id,
                    session_id,
                    agent_run_id,
                    step_id,
                    stable.name,
                    dumps_json(stable.arguments),
                    stable.arguments_raw,
                    stable.parse_error,
                    result_json,
                    ts,
                ),
            )
            self._store.commit()
        except sqlite3.IntegrityError as exc:
            raise ConflictError(f"ToolCall 已存在: {stable.id}") from exc
        except sqlite3.Error as exc:
            raise RepositoryError(f"写入 ToolCall 失败: {exc}") from exc
        return PersistedToolCall(
            tool_call_id=stable.id,
            session_id=session_id,
            agent_run_id=agent_run_id,
            step_id=step_id,
            tool_name=stable.name,
            arguments=dict(stable.arguments),
            arguments_raw=stable.arguments_raw,
            parse_error=stable.parse_error,
            result=result,
            created_at=ts,
        )

#获取一次agent步骤中的多个工具调用
    def list_tool_calls(
        self,
        *,
        step_id: str | None = None,
        agent_run_id: str | None = None,
    ) -> list[PersistedToolCall]:
        if step_id is None and agent_run_id is None:
            raise ValueError("必须提供 step_id 或 agent_run_id")
        if step_id is not None:
            rows = self._store.execute(
                """
                SELECT * FROM tool_calls WHERE step_id = ?
                ORDER BY COALESCE(created_at, '') ASC, id ASC
                """,
                (step_id,),
            ).fetchall()
        else:
            rows = self._store.execute(
                """
                SELECT * FROM tool_calls WHERE agent_run_id = ?
                ORDER BY COALESCE(created_at, '') ASC, id ASC
                """,
                (agent_run_id,),
            ).fetchall()
        return [_row_to_tool_call(row) for row in rows]

#获取一个工具调用
    def get_tool_call(self, tool_call_id: str) -> PersistedToolCall:
        row = self._store.execute(
            "SELECT * FROM tool_calls WHERE id = ?",
            (tool_call_id,),
        ).fetchone()
        if row is None:
            raise NotFoundError(f"ToolCall 不存在: {tool_call_id}")
        return _row_to_tool_call(row)

#将数据库行转换为agent工作过程对象
def _row_to_run(row: sqlite3.Row) -> AgentRun:
    return AgentRun(
        agent_run_id=row["id"],
        session_id=row["session_id"],
        provider_id=row["provider_id"],
        model_id=row["model_id"],
        status=row["status"],
        termination_reason=row["termination_reason"],
        max_steps=row["max_steps"],
        final_answer=row["final_answer"],
        error=row["error"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )

#将数据库行转换为agent工作步骤对象
def _row_to_step(row: sqlite3.Row) -> AgentStep:
    return AgentStep(
        step_id=row["id"],
        agent_run_id=row["agent_run_id"],
        session_id=row["session_id"],
        step_index=row["step_index"],
        status=row["status"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )

#将数据库行转换为工具调用对象
def _row_to_tool_call(row: sqlite3.Row) -> PersistedToolCall:
    arguments = loads_json(row["arguments_json"], default={})
    if not isinstance(arguments, dict):
        arguments = {}
    result = None
    if row["result_json"]:
        raw = loads_json(row["result_json"], default=None)
        if isinstance(raw, dict):
            result = ToolResult.from_dict(raw)
    return PersistedToolCall(
        tool_call_id=row["id"],
        session_id=row["session_id"],
        agent_run_id=row["agent_run_id"],
        step_id=row["step_id"],
        tool_name=row["tool_name"],
        arguments=arguments,
        arguments_raw=row["arguments_raw"],
        parse_error=row["parse_error"],
        result=result,
        created_at=row["created_at"],
    )
