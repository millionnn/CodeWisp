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
        """序列化，供测试、CLI 调试、Observation 持久化与未来 Trace UI 使用。"""
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ToolResult:
        """自 dict 还原；与 ``to_dict`` round-trip。"""
        if not isinstance(data, dict):
            raise TypeError("ToolResult.from_dict 需要 dict")
        success = data.get("success")
        if not isinstance(success, bool):
            raise ValueError("success 必须是 bool")
        metadata = data.get("metadata") or {}
        if not isinstance(metadata, dict):
            raise ValueError("metadata 必须是 dict")
        error = data.get("error")
        if error is not None and not isinstance(error, str):
            raise ValueError("error 必须是字符串或 None")
        return cls(
            success=success,
            output=data.get("output"),
            error=error,
            metadata=dict(metadata),
        )
