"""默认工具注册工厂。"""

from __future__ import annotations

from backend.app.tools.builtin.calculator import CalculatorTool
from backend.app.tools.builtin.time import GetCurrentTimeTool
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.registry import ToolRegistry


def create_default_registry() -> ToolRegistry:
    """创建并注册 V0.2 内置工具。"""
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(GetCurrentTimeTool())
    return registry


def create_default_executor() -> ToolExecutor:
    """创建绑定默认注册表的执行器。"""
    return ToolExecutor(create_default_registry())
