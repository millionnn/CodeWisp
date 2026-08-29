"""run_command：在工作区内执行受控开发命令。"""

from __future__ import annotations

from typing import Any

from backend.app.execution.policy import CommandPolicy, PolicyAction
from backend.app.execution.request import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    ExecutionRequest,
)
from backend.app.execution.result import PermissionRequired
from backend.app.execution.service import ExecutionService
from backend.app.tools.base import Tool
from backend.app.tools.result import ToolResult


class RunCommandTool(Tool):
    """薄封装：Request → Policy →（ALLOW 时）Service → ToolResult。"""

    def __init__(
        self,
        service: ExecutionService,
        policy: CommandPolicy | None = None,
    ) -> None:
        self._service = service
        self._policy = policy if policy is not None else CommandPolicy()

    @property
    def name(self) -> str:
        return "run_command"

    @property
    def description(self) -> str:
        return (
            "在工作区内执行受控的开发/测试/构建命令。"
            "命令必须遵循当前执行策略，并且工作目录必须位于工作区内。"
            "对于需要用户授权的命令，工具会返回 permission_required，"
            "而不会绕过权限策略直接执行。"
            "不要把整段 shell 脚本当作 command；请使用 command + args 列表。"
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": "可执行命令名（如 pytest、npm、python），不要拼 shell 字符串",
                },
                "args": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "参数列表，默认 []",
                },
                "cwd": {
                    "type": "string",
                    "description": "工作目录（相对 workspace），默认 .",
                },
                "timeout": {
                    "type": "number",
                    "description": (
                        f"超时秒数，默认 {DEFAULT_TIMEOUT_SECONDS}，"
                        f"上限 {MAX_TIMEOUT_SECONDS}"
                    ),
                },
            },
            "required": ["command"],
        }

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        command = str(arguments.get("command", "") or "")
        raw_args = arguments.get("args")
        if raw_args is None:
            args: list[str] = []
        elif isinstance(raw_args, list):
            args = [str(a) for a in raw_args]
        else:
            return ToolResult(
                success=False,
                output=None,
                error="args 必须是字符串数组。",
            )

        cwd = arguments.get("cwd", ".")
        timeout = arguments.get("timeout", DEFAULT_TIMEOUT_SECONDS)
        try:
            request = ExecutionRequest(
                command=command,
                args=args,
                cwd=str(cwd) if cwd is not None else ".",
                timeout=float(timeout),
            )
        except Exception as exc:  # noqa: BLE001 — 构造期非法 → 结构化失败
            return ToolResult(success=False, output=None, error=str(exc))

        decision = self._policy.decide(request)

        if decision.action is PolicyAction.DENY:
            return ToolResult(
                success=False,
                output={
                    "denied": True,
                    "decision": decision.to_dict(),
                    "command": request.command,
                    "args": list(request.args),
                    "cwd": request.cwd,
                },
                error=decision.reason,
                metadata={
                    "tool_name": self.name,
                    "policy_action": decision.action.value,
                },
            )

        if decision.action is PolicyAction.ASK:
            permission = PermissionRequired(
                command=request.command,
                args=request.args,
                cwd=request.cwd,
                reason=decision.reason,
            )
            return ToolResult(
                success=False,
                output=permission.to_dict(),
                error=decision.reason,
                metadata={
                    "tool_name": self.name,
                    "policy_action": decision.action.value,
                    "permission_required": True,
                },
            )

        # ALLOW：真正执行
        result = self._service.run(request)
        return ToolResult(
            success=result.success,
            output=result.to_dict(),
            error=None if result.success else (result.stderr or "命令执行失败。"),
            metadata={
                "tool_name": self.name,
                "policy_action": decision.action.value,
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "truncated": result.truncated,
            },
        )
