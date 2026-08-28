"""ToolResult 测试。"""

from backend.app.tools.result import ToolResult


def test_success_result() -> None:
    result = ToolResult(success=True, output="101", error=None)
    assert result.success is True
    assert result.output == "101"
    assert result.error is None
    assert result.metadata == {}


def test_failure_result() -> None:
    result = ToolResult(success=False, output=None, error="Invalid expression")
    assert result.success is False
    assert result.output is None
    assert result.error == "Invalid expression"


def test_result_to_dict_includes_metadata() -> None:
    result = ToolResult(
        success=True,
        output=1,
        metadata={"tool_name": "calculator", "duration_ms": 1.2},
    )
    data = result.to_dict()
    assert data["success"] is True
    assert data["metadata"]["tool_name"] == "calculator"
