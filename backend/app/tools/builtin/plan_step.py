"""显式完成当前 Plan 步骤（Agent 发信号，再进入下一条）。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.app.tools.base import Tool
from backend.app.tools.result import ToolResult


class CompletePlanStepTool(Tool):
    """将当前 in_progress 的 Plan 步骤标为完成，并激活下一条。"""

    def __init__(
        self,
        complete_fn: Callable[..., dict[str, Any]] | None = None,
    ) -> None:
        self._complete_fn = complete_fn

    @property
    def name(self) -> str:
        return "complete_plan_step"

    @property
    def description(self) -> str:
        return (
            "Mark the current Plan step as completed and move to the next step. "
            "Call this only when the current in_progress step's goal is done. "
            "Do not skip ahead without finishing the current step."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "note": {
                    "type": "string",
                    "description": "Optional short note about what was accomplished.",
                }
            },
            "additionalProperties": False,
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        if self._complete_fn is None:
            return ToolResult(
                success=False,
                output=None,
                error="complete_plan_step 未绑定 Plan（无 ContextManager）。",
                metadata={"tool_name": self.name},
            )
        note = ""
        if isinstance(arguments, dict):
            note = str(arguments.get("note") or "").strip()
        try:
            payload = self._complete_fn(note=note)
        except Exception as exc:  # noqa: BLE001
            return ToolResult(
                success=False,
                output=None,
                error=str(exc),
                metadata={"tool_name": self.name},
            )
        ok = bool(payload.get("ok"))
        return ToolResult(
            success=ok,
            output=payload,
            error=None if ok else str(payload.get("error") or "complete failed"),
            metadata={"tool_name": self.name},
        )


def create_complete_plan_step_tool(
    complete_fn: Callable[..., dict[str, Any]] | None = None,
) -> CompletePlanStepTool:
    return CompletePlanStepTool(complete_fn=complete_fn)
