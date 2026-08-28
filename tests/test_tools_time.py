"""get_current_time 工具测试。"""

from __future__ import annotations

from datetime import datetime

from backend.app.tools.builtin.time import GetCurrentTimeTool
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry


def test_get_current_time_success() -> None:
    tool = GetCurrentTimeTool()
    result = tool.execute({})
    assert result.success is True
    assert isinstance(result.output, dict)
    assert "iso" in result.output
    assert "unix" in result.output
    assert "timezone" in result.output
    # iso 可被解析
    datetime.fromisoformat(result.output["iso"])


def test_get_current_time_via_executor() -> None:
    executor = ToolExecutor(create_default_registry())
    result = executor.execute("get_current_time", {})
    assert result.success is True
    assert result.metadata["tool_name"] == "get_current_time"
    assert "duration_ms" in result.metadata
