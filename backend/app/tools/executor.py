"""工具执行器：按名称查找并执行 Tool，统一返回 ToolResult。

不负责 LLM、Agent Loop、CLI 或 Web API。
"""

from __future__ import annotations

import time
from typing import Any

from backend.app.tools.errors import ToolArgumentError, ToolError, ToolNotFoundError
from backend.app.tools.registry import ToolRegistry
from backend.app.tools.result import ToolResult


class ToolExecutor:
    """统一执行入口：tool_name + arguments → ToolResult。"""

    def __init__(self, registry: ToolRegistry) -> None:
        self.registry = registry

    def execute(self, tool_name: str, arguments: dict[str, Any] | None = None) -> ToolResult:
        """执行指定工具。

        任何可预期失败都以 ToolResult(success=False) 返回，避免拖垮上层循环。
        """
        args = arguments if arguments is not None else {}
        started = time.perf_counter()
        name = (tool_name or "").strip()

        base_meta: dict[str, Any] = {
            "tool_name": name or tool_name,
            "arguments": args,
        }

        if not name:
            return self._failure("工具名称不能为空。", base_meta, started)

        try:
            tool = self.registry.get(name)
        except ToolNotFoundError as exc:
            return self._failure(str(exc), base_meta, started)

        try:
            validated = self._validate_arguments(tool.parameters, args)
        except ToolArgumentError as exc:
            return self._failure(str(exc), base_meta, started)

        try:
            result = tool.execute(validated)
        except ToolError as exc:
            return self._failure(str(exc), base_meta, started)
        except Exception as exc:  # noqa: BLE001 — 边界：工具内部异常结构化
            return self._failure(f"工具执行异常：{exc}", base_meta, started)

        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        metadata = {
            **base_meta,
            "duration_ms": duration_ms,
            **(result.metadata or {}),
        }
        return ToolResult(
            success=result.success,
            output=result.output,
            error=result.error,
            metadata=metadata,
        )

    def _failure(
        self,
        error: str,
        base_meta: dict[str, Any],
        started: float,
    ) -> ToolResult:
        duration_ms = round((time.perf_counter() - started) * 1000, 3)
        return ToolResult(
            success=False,
            output=None,
            error=error,
            metadata={**base_meta, "duration_ms": duration_ms},
        )

    @staticmethod
    def _validate_arguments(
        schema: dict[str, Any],
        arguments: dict[str, Any],
    ) -> dict[str, Any]:
        """对 JSON Schema 子集做轻量校验：required / type / 多余参数。"""
        if not isinstance(arguments, dict):
            raise ToolArgumentError("参数必须是对象（dict）。")

        if schema.get("type", "object") != "object":
            raise ToolArgumentError("当前仅支持 object 类型的参数 schema。")

        properties: dict[str, Any] = schema.get("properties") or {}
        required: list[str] = list(schema.get("required") or [])

        missing = [key for key in required if key not in arguments]
        if missing:
            raise ToolArgumentError(f"缺少必需参数：{', '.join(missing)}")

        extra = [key for key in arguments if key not in properties]
        if extra:
            raise ToolArgumentError(f"存在未声明参数：{', '.join(sorted(extra))}")

        type_map = {
            "string": str,
            "number": (int, float),
            "integer": int,
            "boolean": bool,
            "object": dict,
            "array": list,
            "null": type(None),
        }

        for key, value in arguments.items():
            prop = properties.get(key) or {}
            expected = prop.get("type")
            if expected is None:
                continue
            py_type = type_map.get(expected)
            if py_type is None:
                continue
            # JSON number 允许 int/float；布尔值不要被当成 int 误判通过。
            if expected == "number":
                if isinstance(value, bool) or not isinstance(value, (int, float)):
                    raise ToolArgumentError(f"参数 {key} 类型错误，期望 number。")
            elif expected == "integer":
                if isinstance(value, bool) or not isinstance(value, int):
                    raise ToolArgumentError(f"参数 {key} 类型错误，期望 integer。")
            elif not isinstance(value, py_type):
                raise ToolArgumentError(f"参数 {key} 类型错误，期望 {expected}。")

        return arguments
