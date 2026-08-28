"""ToolExecutor 测试。"""

from __future__ import annotations

from typing import Any

import pytest

from backend.app.tools.base import Tool
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry
from backend.app.tools.registry import ToolRegistry
from backend.app.tools.result import ToolResult


class _BoomTool(Tool):
    @property
    def name(self) -> str:
        return "boom"

    @property
    def description(self) -> str:
        return "always fails"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {"x": {"type": "string"}},
            "required": ["x"],
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        raise RuntimeError("内部爆炸")


@pytest.fixture
def executor() -> ToolExecutor:
    return ToolExecutor(create_default_registry())


def test_executor_normal(executor: ToolExecutor) -> None:
    result = executor.execute("calculator", {"expression": "2 + 2"})
    assert result.success is True
    assert result.output == 4
    assert result.metadata["tool_name"] == "calculator"
    assert result.metadata["arguments"] == {"expression": "2 + 2"}
    assert "duration_ms" in result.metadata


def test_executor_tool_not_found(executor: ToolExecutor) -> None:
    result = executor.execute("no_such_tool", {})
    assert result.success is False
    assert "未找到" in (result.error or "")


def test_executor_missing_required(executor: ToolExecutor) -> None:
    result = executor.execute("calculator", {})
    assert result.success is False
    assert "缺少必需参数" in (result.error or "")


def test_executor_wrong_type(executor: ToolExecutor) -> None:
    result = executor.execute("calculator", {"expression": 123})
    assert result.success is False
    assert "类型错误" in (result.error or "")


def test_executor_extra_argument(executor: ToolExecutor) -> None:
    result = executor.execute(
        "calculator",
        {"expression": "1+1", "extra": "nope"},
    )
    assert result.success is False
    assert "未声明参数" in (result.error or "")


def test_executor_empty_tool_name(executor: ToolExecutor) -> None:
    result = executor.execute("  ", {})
    assert result.success is False
    assert "不能为空" in (result.error or "")


def test_executor_internal_exception() -> None:
    registry = ToolRegistry()
    registry.register(_BoomTool())
    executor = ToolExecutor(registry)
    result = executor.execute("boom", {"x": "1"})
    assert result.success is False
    assert "工具执行异常" in (result.error or "")
