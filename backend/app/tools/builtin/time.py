"""返回本地当前时间（不依赖外部网络）。"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from backend.app.tools.base import Tool
from backend.app.tools.result import ToolResult


class GetCurrentTimeTool(Tool):
    """获取本机当前时间。"""

    @property
    def name(self) -> str:
        return "get_current_time"

    @property
    def description(self) -> str:
        return "返回本机当前日期时间（ISO 8601 格式），不依赖外部网络。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {},
            "required": [],
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        _ = arguments
        now = datetime.now().astimezone()
        payload = {
            "iso": now.isoformat(timespec="seconds"),
            "timezone": str(now.tzinfo),
            "unix": int(now.timestamp()),
        }
        return ToolResult(success=True, output=payload, error=None)
