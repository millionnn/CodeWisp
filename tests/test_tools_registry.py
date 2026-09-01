"""ToolRegistry 测试。"""

from __future__ import annotations

from typing import Any

import pytest

from backend.app.tools.base import Tool
from backend.app.tools.errors import ToolNotFoundError, ToolRegistrationError
from backend.app.tools.registry import ToolRegistry
from backend.app.tools.result import ToolResult


class _DummyTool(Tool):
    def __init__(self, name: str = "dummy") -> None:
        self._name = name

    @property
    def name(self) -> str:
        return self._name

    @property
    def description(self) -> str:
        return "dummy tool"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(success=True, output=arguments)


def test_register_get_contains_list() -> None:
    registry = ToolRegistry()
    tool = _DummyTool("alpha")
    registry.register(tool)

    assert registry.contains("alpha")
    assert registry.get("alpha") is tool
    assert [t.name for t in registry.list_tools()] == ["alpha"]
    assert len(registry) == 1


def test_duplicate_registration() -> None:
    registry = ToolRegistry()
    registry.register(_DummyTool("alpha"))
    with pytest.raises(ToolRegistrationError, match="重复"):
        registry.register(_DummyTool("alpha"))


def test_unknown_tool() -> None:
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError, match="未找到"):
        registry.get("missing")


def test_empty_name_on_get_and_register() -> None:
    registry = ToolRegistry()
    with pytest.raises(ToolNotFoundError, match="不能为空"):
        registry.get("")
    with pytest.raises(ToolRegistrationError, match="不能为空"):
        registry.register(_DummyTool("  "))


def test_unregister_and_replace() -> None:
    registry = ToolRegistry()
    registry.register(_DummyTool("alpha"))
    registry.register_or_replace(_DummyTool("alpha"))
    assert registry.contains("alpha")
    assert registry.unregister("alpha") is True
    assert registry.unregister("alpha") is False
    assert not registry.contains("alpha")


def test_list_schemas() -> None:
    registry = ToolRegistry()
    registry.register(_DummyTool("alpha"))
    schemas = registry.list_schemas()
    assert schemas[0]["function"]["name"] == "alpha"

