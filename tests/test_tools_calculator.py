"""calculator 工具与安全求值测试。"""

from __future__ import annotations

import pytest

from backend.app.tools.builtin.calculator import CalculatorTool, safe_calculate
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry


@pytest.fixture
def calculator() -> CalculatorTool:
    return CalculatorTool()


@pytest.fixture
def executor() -> ToolExecutor:
    return ToolExecutor(create_default_registry())


def test_normal_expression(executor: ToolExecutor) -> None:
    result = executor.execute("calculator", {"expression": "12 * 8 + 5"})
    assert result.success is True
    assert result.output == 101


def test_decimal(calculator: CalculatorTool) -> None:
    result = calculator.execute({"expression": "1.5 * 2"})
    assert result.success is True
    assert result.output == 3


def test_negative(calculator: CalculatorTool) -> None:
    result = calculator.execute({"expression": "-3 + 10"})
    assert result.success is True
    assert result.output == 7


def test_illegal_expression(calculator: CalculatorTool) -> None:
    result = calculator.execute({"expression": "1 +"})
    assert result.success is False
    assert result.error is not None


def test_empty_expression(calculator: CalculatorTool) -> None:
    result = calculator.execute({"expression": "   "})
    assert result.success is False
    assert "空" in (result.error or "")


def test_dangerous_input_rejected(calculator: CalculatorTool) -> None:
    dangerous = [
        "__import__('os').system('echo hacked')",
        "open('/etc/passwd').read()",
        "(lambda: 1)()",
        "a + 1",
        "abs(1)",
    ]
    for expr in dangerous:
        result = calculator.execute({"expression": expr})
        assert result.success is False, expr


def test_division_by_zero(calculator: CalculatorTool) -> None:
    result = calculator.execute({"expression": "1 / 0"})
    assert result.success is False
    assert "0" in (result.error or "")


def test_safe_calculate_direct() -> None:
    assert safe_calculate("(1 + 2) * 3") == 9
