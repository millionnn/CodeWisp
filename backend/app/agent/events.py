"""轻量 Agent 事件，为未来 Trace UI 预留结构化数据（无 Event Bus）。"""

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
