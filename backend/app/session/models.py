"""Session / AgentRun / AgentStep 领域模型（V0.6 Phase 2-A）。

仅负责内存表示与 round-trip 序列化；不访问 SQLite。
AgentRun.provider_id / model_id 为该次运行的模型身份快照。
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.session.ids import new_agent_run_id, new_session_id, new_step_id


def _require_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"缺少或非法字段: {key}")
    return value


def _optional_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError(f"字段 {key} 必须是字符串或 None")
    return value


@dataclass(frozen=True)
class Session:
    """一条持续的 Agent 工作线程（绑定 workspace 与默认模型身份）。"""

    session_id: str
    title: str
    workspace: str
    provider_id: str
    model_id: str
    status: str = "active"
    created_at: str | None = None
    updated_at: str | None = None

    @classmethod
    def create(
        cls,
        *,
        title: str,
        workspace: str,
        provider_id: str = "deepseek",
        model_id: str = "deepseek-chat",
        status: str = "active",
        session_id: str | None = None,
        created_at: str | None = None,
        updated_at: str | None = None,
    ) -> Session:
        return cls(
            session_id=session_id or new_session_id(),
            title=title,
            workspace=workspace,
            provider_id=provider_id,
            model_id=model_id,
            status=status,
            created_at=created_at,
            updated_at=updated_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "session_id": self.session_id,
            "title": self.title,
            "workspace": self.workspace,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "status": self.status,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Session:
        if not isinstance(data, dict):
            raise TypeError("Session.from_dict 需要 dict")
        return cls(
            session_id=_require_str(data, "session_id"),
            title=_require_str(data, "title"),
            workspace=_require_str(data, "workspace"),
            provider_id=_require_str(data, "provider_id"),
            model_id=_require_str(data, "model_id"),
            status=str(data.get("status") or "active"),
            created_at=_optional_str(data, "created_at"),
            updated_at=_optional_str(data, "updated_at"),
        )


@dataclass(frozen=True)
class AgentRun:
    """一次 AgentLoop.run 的持久化投影（含 provider/model 快照）。"""

    agent_run_id: str
    session_id: str
    provider_id: str
    model_id: str
    status: str
    termination_reason: str | None = None
    max_steps: int = 15
    final_answer: str | None = None
    error: str | None = None
    created_at: str | None = None
    completed_at: str | None = None

    @classmethod
    def create(
        cls,
        *,
        session_id: str,
        provider_id: str,
        model_id: str,
        status: str = "running",
        max_steps: int = 15,
        agent_run_id: str | None = None,
        termination_reason: str | None = None,
        final_answer: str | None = None,
        error: str | None = None,
        created_at: str | None = None,
        completed_at: str | None = None,
    ) -> AgentRun:
        # status 使用字符串，与 AgentStatus.value 对齐；避免依赖 agent.state 造成循环导入
        status_value = getattr(status, "value", None) or str(status)
        return cls(
            agent_run_id=agent_run_id or new_agent_run_id(),
            session_id=session_id,
            provider_id=provider_id,
            model_id=model_id,
            status=str(status_value),
            termination_reason=termination_reason,
            max_steps=max_steps,
            final_answer=final_answer,
            error=error,
            created_at=created_at,
            completed_at=completed_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_run_id": self.agent_run_id,
            "session_id": self.session_id,
            "provider_id": self.provider_id,
            "model_id": self.model_id,
            "status": self.status,
            "termination_reason": self.termination_reason,
            "max_steps": self.max_steps,
            "final_answer": self.final_answer,
            "error": self.error,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentRun:
        if not isinstance(data, dict):
            raise TypeError("AgentRun.from_dict 需要 dict")
        max_steps = data.get("max_steps", 15)
        if not isinstance(max_steps, int) or isinstance(max_steps, bool):
            raise ValueError("max_steps 必须是 int")
        return cls(
            agent_run_id=_require_str(data, "agent_run_id"),
            session_id=_require_str(data, "session_id"),
            provider_id=_require_str(data, "provider_id"),
            model_id=_require_str(data, "model_id"),
            status=_require_str(data, "status"),
            termination_reason=_optional_str(data, "termination_reason"),
            max_steps=max_steps,
            final_answer=_optional_str(data, "final_answer"),
            error=_optional_str(data, "error"),
            created_at=_optional_str(data, "created_at"),
            completed_at=_optional_str(data, "completed_at"),
        )


@dataclass(frozen=True)
class AgentStep:
    """AgentRun 内一次 LLM 调用对应的 Step（稳定 step_id，非数组下标）。"""

    step_id: str
    agent_run_id: str
    session_id: str
    step_index: int
    status: str = "completed"
    created_at: str | None = None
    completed_at: str | None = None

    @classmethod
    def create(
        cls,
        *,
        agent_run_id: str,
        session_id: str,
        step_index: int,
        status: str = "completed",
        step_id: str | None = None,
        created_at: str | None = None,
        completed_at: str | None = None,
    ) -> AgentStep:
        if step_index < 1:
            raise ValueError("step_index 必须 >= 1")
        return cls(
            step_id=step_id or new_step_id(),
            agent_run_id=agent_run_id,
            session_id=session_id,
            step_index=step_index,
            status=status,
            created_at=created_at,
            completed_at=completed_at,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_id": self.step_id,
            "agent_run_id": self.agent_run_id,
            "session_id": self.session_id,
            "step_index": self.step_index,
            "status": self.status,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentStep:
        if not isinstance(data, dict):
            raise TypeError("AgentStep.from_dict 需要 dict")
        step_index = data.get("step_index")
        if not isinstance(step_index, int) or isinstance(step_index, bool) or step_index < 1:
            raise ValueError("step_index 必须是 >= 1 的 int")
        return cls(
            step_id=_require_str(data, "step_id"),
            agent_run_id=_require_str(data, "agent_run_id"),
            session_id=_require_str(data, "session_id"),
            step_index=step_index,
            status=str(data.get("status") or "completed"),
            created_at=_optional_str(data, "created_at"),
            completed_at=_optional_str(data, "completed_at"),
        )
