"""Agent 运行状态。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from backend.app.agent.events import AgentEvent
from backend.app.llm.messages import Conversation
from backend.app.llm.response import ToolCall


class AgentStatus(str, Enum):
    IDLE = "idle"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    MAX_STEPS = "max_steps"
    # V0.5：遇 ASK / permission_required 时框架硬停（不自动授权）
    PERMISSION_REQUIRED = "permission_required"


@dataclass
class AgentState:
    """一次 AgentLoop.run 的结果快照。"""

    status: AgentStatus = AgentStatus.IDLE
    step: int = 0
    max_steps: int = 15
    conversation: Conversation = field(default_factory=Conversation)
    final_answer: str | None = None
    error: str | None = None
    # 终止原因：completed / max_steps / permission_required / failed / ...
    termination_reason: str | None = None
    last_tool_calls: tuple[ToolCall, ...] = ()
    events: list[AgentEvent] = field(default_factory=list)
