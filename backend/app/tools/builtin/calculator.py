"""安全计算器：仅解析加减乘除等算术表达式，禁止 eval 任意代码。"""

from __future__ import annotations

import ast
import operator
from typing import Any

from backend.app.tools.base import Tool
from backend.app.tools.result import ToolResult

_BIN_OPS: dict[type[ast.operator], Any] = {
    ast.Add: operator.add,
    ast.Sub: operator.sub,
    ast.Mult: operator.mul,
    ast.Div: operator.truediv,
    ast.FloorDiv: operator.floordiv,
    ast.Mod: operator.mod,
    ast.Pow: operator.pow,
}

_UNARY_OPS: dict[type[ast.unaryop], Any] = {
    ast.UAdd: operator.pos,
    ast.USub: operator.neg,
}


def _eval_node(node: ast.AST) -> int | float:
    """递归求值 AST；只允许数字与安全运算符。"""
    if isinstance(node, ast.Constant):
        if isinstance(node.value, bool) or not isinstance(node.value, (int, float)):
            raise ValueError("表达式只能包含数字。")
        return node.value

    if isinstance(node, ast.UnaryOp):
        op = _UNARY_OPS.get(type(node.op))
        if op is None:
            raise ValueError("不支持的一元运算符。")
        return op(_eval_node(node.operand))

    if isinstance(node, ast.BinOp):
        op = _BIN_OPS.get(type(node.op))
        if op is None:
            raise ValueError("不支持的二元运算符。")
        left = _eval_node(node.left)
        right = _eval_node(node.right)
        if isinstance(node.op, (ast.Div, ast.FloorDiv, ast.Mod)) and right == 0:
            raise ValueError("除数不能为 0。")
        # 限制幂运算规模，避免恶意大指数拖垮进程。
        if isinstance(node.op, ast.Pow):
            if abs(right) > 1000 or abs(left) > 10**6:
                raise ValueError("幂运算数值过大，已拒绝执行。")
        return op(left, right)

    # 明确拒绝名称、调用、属性访问等危险节点。
    raise ValueError(f"不允许的表达式结构：{type(node).__name__}")


def safe_calculate(expression: str) -> int | float:
    """安全计算数学表达式。"""
    text = expression.strip()
    if not text:
        raise ValueError("表达式不能为空。")
    if len(text) > 200:
        raise ValueError("表达式过长。")

    try:
        tree = ast.parse(text, mode="eval")
    except SyntaxError as exc:
        raise ValueError(f"非法表达式：{exc.msg}") from exc

    value = _eval_node(tree.body)
    # 尽量返回更干净的 int（例如 101.0 → 101）。
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return value


class CalculatorTool(Tool):
    """计算简单数学表达式。"""

    @property
    def name(self) -> str:
        return "calculator"

    @property
    def description(self) -> str:
        return "安全计算简单数学表达式，支持加减乘除、整除、取模与幂运算。"

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "expression": {
                    "type": "string",
                    "description": "要计算的数学表达式，例如 '12 * 8 + 5'",
                }
            },
            "required": ["expression"],
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        expression = arguments.get("expression", "")
        try:
            value = safe_calculate(str(expression))
        except ValueError as exc:
            return ToolResult(success=False, output=None, error=str(exc))
        return ToolResult(success=True, output=value, error=None)
