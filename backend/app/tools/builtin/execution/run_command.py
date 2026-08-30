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
from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.errors import PermissionInterruptedError
from backend.app.permissions.handler import PermissionHandler
from backend.app.permissions.request import PermissionRequest
from backend.app.tools.base import Tool
from backend.app.tools.result import ToolResult


class RunCommandTool(Tool):
    """薄封装：Request → Policy →（ASK 时 Handler）→ Service → ToolResult。"""

    def __init__(
        self,
        service: ExecutionService,
        policy: CommandPolicy | None = None,
        *,
        permission_handler: PermissionHandler | None = None,
        session_id: str | None = None,
        agent_run_id: str | None = None,
        on_permission_wait: Any | None = None,
        on_permission_resolved: Any | None = None,
        on_command_line: Any | None = None,
    ) -> None:
        self._service = service
        self._policy = policy if policy is not None else CommandPolicy()
        self._permission_handler = permission_handler
        self._session_id = session_id
        self._agent_run_id = agent_run_id
        self._on_permission_wait = on_permission_wait
        self._on_permission_resolved = on_permission_resolved
        self._on_command_line = on_command_line

    @property
    def name(self) -> str:
        return "run_command"

    @property
    def description(self) -> str:
        return (
            "在工作区内执行受控的开发/测试/构建命令。"
            "命令必须遵循当前执行策略，并且工作目录必须位于工作区内。"
            "对于需要用户授权的命令：若运行时提供了 PermissionHandler，"
            "将交互征求 ALLOW/DENY；否则返回 permission_required 并停止自动继续。"
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
        except Exception as exc:  # noqa: BLE001
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
            return self._handle_ask(request, decision.reason)

        return self._execute_allow(request)

    def _handle_ask(self, request: ExecutionRequest, reason: str) -> ToolResult:
        # 无 Handler：V0.7 兼容 — 返回 permission_required，由 Loop 硬停
        if self._permission_handler is None:
            permission = PermissionRequired(
                command=request.command,
                args=request.args,
                cwd=request.cwd,
                reason=reason,
            )
            return ToolResult(
                success=False,
                output=permission.to_dict(),
                error=reason,
                metadata={
                    "tool_name": self.name,
                    "policy_action": PolicyAction.ASK.value,
                    "permission_required": True,
                },
            )

        perm_req = PermissionRequest(
            command=request.command,
            args=tuple(request.args),
            cwd=request.cwd,
            reason=reason,
            tool_name=self.name,
            session_id=self._session_id,
            agent_run_id=self._agent_run_id,
        )
        if self._on_permission_wait is not None:
            self._on_permission_wait(perm_req)

        try:
            user_decision = self._permission_handler.request(perm_req)
        except PermissionInterruptedError as exc:
            if self._on_permission_resolved is not None:
                self._on_permission_resolved(perm_req, None)
            return ToolResult(
                success=False,
                output={
                    "denied": True,
                    "user_denied": True,
                    "interrupted": True,
                    "command": request.command,
                    "args": list(request.args),
                    "cwd": request.cwd,
                    "permission_request_id": perm_req.request_id,
                },
                error=str(exc),
                metadata={
                    "tool_name": self.name,
                    "policy_action": PolicyAction.ASK.value,
                    "permission_decision": "interrupted",
                },
            )

        if self._on_permission_resolved is not None:
            self._on_permission_resolved(perm_req, user_decision)

        if user_decision is PermissionDecision.ALLOW:
            result = self._execute_allow(request)
            result.metadata = {
                **(result.metadata or {}),
                "permission_decision": PermissionDecision.ALLOW.value,
                "permission_request_id": perm_req.request_id,
            }
            return result

        # 用户 DENY：写入 observation，不设 permission_required（Loop 可继续）
        return ToolResult(
            success=False,
            output={
                "denied": True,
                "user_denied": True,
                "command": request.command,
                "args": list(request.args),
                "cwd": request.cwd,
                "permission_request_id": perm_req.request_id,
                "reason": reason,
            },
            error="用户拒绝执行该命令（DENY）。",
            metadata={
                "tool_name": self.name,
                "policy_action": PolicyAction.ASK.value,
                "permission_decision": PermissionDecision.DENY.value,
            },
        )

    def _execute_allow(self, request: ExecutionRequest) -> ToolResult:
        if self._on_command_line is not None:
            result = self._service.run(request, on_line=self._on_command_line)
        else:
            result = self._service.run(request)
        return ToolResult(
            success=result.success,
            output=result.to_dict(),
            error=None if result.success else (result.stderr or "命令执行失败。"),
            metadata={
                "tool_name": self.name,
                "policy_action": PolicyAction.ALLOW.value,
                "exit_code": result.exit_code,
                "timed_out": result.timed_out,
                "truncated": result.truncated,
            },
        )
