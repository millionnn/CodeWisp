"""工具注册表：注册、查找、列举。"""

from __future__ import annotations

from backend.app.tools.base import Tool
from backend.app.tools.errors import ToolNotFoundError, ToolRegistrationError


class ToolRegistry:
    """按名称管理 Tool 实例。"""

    def __init__(self) -> None:
        self._tools: dict[str, Tool] = {}

    def register(self, tool: Tool) -> None:
        """注册工具；名称必须非空且不可重复。"""
        name = (tool.name or "").strip()
        if not name:
            raise ToolRegistrationError("工具名称不能为空。")
        if name in self._tools:
            raise ToolRegistrationError(f"工具已注册，禁止重复：{name}")
        self._tools[name] = tool

    def get(self, name: str) -> Tool:
        """按名称获取工具；不存在则抛出 ToolNotFoundError。"""
        key = (name or "").strip()
        if not key:
            raise ToolNotFoundError("工具名称不能为空。")
        tool = self._tools.get(key)
        if tool is None:
            raise ToolNotFoundError(f"未找到工具：{key}")
        return tool

    def contains(self, name: str) -> bool:
        key = (name or "").strip()
        return key in self._tools

    def list_tools(self) -> list[Tool]:
        """返回已注册工具列表（按名称排序，便于稳定展示）。"""
        return [self._tools[k] for k in sorted(self._tools)]

    def list_schemas(self) -> list[dict]:
        """导出全部工具 schema，供未来 Agent Loop / LLM 使用。"""
        return [tool.to_schema() for tool in self.list_tools()]

    def __len__(self) -> int:
        return len(self._tools)
