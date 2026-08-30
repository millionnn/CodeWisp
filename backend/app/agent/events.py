"""轻量 Agent 事件，为未来 Trace UI / Persistence Adapter 预留结构化数据（无 Event Bus）。

V0.6 AgentStep 生命周期与现有 event_type 对齐（不另造第二套事件系统）：

```text
step 开始概念  ← llm_called 之前（可由 Persistence 在进入 step 时记录）
LLM response   ← llm_called
tool calls     ← tool_called
observations   ← tool_completed / tool_failed
step 结束      ← 下一步 llm_called 之前，或 agent_completed
```

Persistence Adapter（后续 Phase）应消费这些事件 + AgentState.step，
映射为稳定 ``step_id`` / ``tool_call_id``，而不是改写 AgentLoop。
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class AgentEvent:
    """单条 Agent 执行事件。"""

    event_type: str
    step: int
    timestamp: float = field(default_factory=time.time)
    tool_name: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> AgentEvent:
        if not isinstance(data, dict):
            raise TypeError("AgentEvent.from_dict 需要 dict")
        event_type = data.get("event_type")
        if not isinstance(event_type, str) or not event_type:
            raise ValueError("event_type 必须是非空字符串")
        step = data.get("step")
        if not isinstance(step, int) or isinstance(step, bool) or step < 0:
            raise ValueError("step 必须是 >= 0 的 int")
        timestamp = data.get("timestamp", time.time())
        if not isinstance(timestamp, (int, float)) or isinstance(timestamp, bool):
            raise ValueError("timestamp 必须是 number")
        tool_name = data.get("tool_name")
        if tool_name is not None and not isinstance(tool_name, str):
            raise ValueError("tool_name 必须是字符串或 None")
        metadata = data.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata 必须是 dict")
        return cls(
            event_type=event_type,
            step=step,
            timestamp=float(timestamp),
            tool_name=tool_name,
            metadata=dict(metadata),
        )
