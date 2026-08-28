"""统一的工具执行结果。

所有 Tool 必须返回 ToolResult，便于未来 Agent Loop 统一处理：
Tool Call → ToolResult → Observation。
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass
class ToolResult:
    """结构化工具执行结果。"""

    success: bool
    output: Any | None = None
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """序列化，供测试、CLI 调试与未来 Trace UI 使用。"""
        return asdict(self)
