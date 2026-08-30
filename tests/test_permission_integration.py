"""V0.8：ASK + PermissionHandler 与 Execution / AgentLoop 集成。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.agent.loop import AgentLoop
from backend.app.agent.state import AgentStatus
from backend.app.execution.policy import CommandPolicy, PolicyAction
from backend.app.execution.request import ExecutionRequest
from backend.app.execution.result import ExecutionResult
from backend.app.execution.service import ExecutionService
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.handler import ScriptedPermissionHandler
from backend.app.tools.builtin.execution.run_command import RunCommandTool
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry
from backend.app.workspace.workspace import Workspace


class ScriptedLLMClient(LLMClient):
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.config = LLMConfig(api_key="fake", base_url="http://localhost", model="fake")
        self._client = None  # type: ignore[assignment]
        self._queue = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        conversation: Conversation,
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        self.calls.append({"messages": conversation.to_api_messages(), "tools": tools})
        if not self._queue:
            raise LLMRequestError("无更多脚本响应")
        return self._queue.pop(0)


class SpyExecutionService(ExecutionService):
    def __init__(self, workspace: Workspace) -> None:
        super().__init__(workspace)
        self.calls: list[ExecutionRequest] = []

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        self.calls.append(request)
        return ExecutionResult(
            success=True,
            exit_code=0,
            stdout="ok",
            stderr="",
            duration_ms=1.0,
            command=request.command,
            args=list(request.args),
            cwd=str(request.cwd),
            timed_out=False,
            truncated=False,
        )


def test_ask_allow_executes_command(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    spy = SpyExecutionService(ws)
    handler = ScriptedPermissionHandler([PermissionDecision.ALLOW])
    tool = RunCommandTool(spy, CommandPolicy(), permission_handler=handler)
    result = tool.execute({"command": "npm", "args": ["install"]})
    assert result.success is True
    assert result.metadata.get("permission_decision") == "allow"
    assert len(spy.calls) == 1
    assert len(handler.requests) == 1


def test_ask_deny_does_not_execute(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    spy = SpyExecutionService(ws)
    handler = ScriptedPermissionHandler([PermissionDecision.DENY])
    tool = RunCommandTool(spy, CommandPolicy(), permission_handler=handler)
    result = tool.execute({"command": "npm", "args": ["install"]})
    assert result.success is False
    assert result.output["user_denied"] is True
    assert result.metadata.get("permission_required") is not True
    assert spy.calls == []


def test_deny_policy_never_calls_handler(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    spy = SpyExecutionService(ws)
    handler = ScriptedPermissionHandler([PermissionDecision.ALLOW])
    tool = RunCommandTool(spy, CommandPolicy(), permission_handler=handler)
    result = tool.execute({"command": "sudo", "args": ["ls"]})
    assert result.success is False
    assert result.metadata.get("policy_action") == PolicyAction.DENY.value
    assert handler.requests == []
    assert spy.calls == []


def test_no_handler_ask_still_permission_required(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    spy = SpyExecutionService(ws)
    tool = RunCommandTool(spy, CommandPolicy())
    result = tool.execute({"command": "npm", "args": ["install"]})
    assert result.metadata.get("permission_required") is True
    assert spy.calls == []


def test_ask_allow_agent_loop_continues(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    spy = SpyExecutionService(ws)
    handler = ScriptedPermissionHandler([PermissionDecision.ALLOW])
    registry = create_default_registry(
        workspace=ws,
        execution_service=spy,
        permission_handler=handler,
    )
    executor = ToolExecutor(registry)
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="run_command",
                        arguments={"command": "npm", "args": ["install"]},
                        arguments_raw='{"command":"npm","args":["install"]}',
                    ),
                ),
            ),
            LLMResponse(content="安装完成", tool_calls=()),
        ]
    )
    state = AgentLoop(llm, executor, registry, max_steps=5).run("npm install")
    assert state.status == AgentStatus.COMPLETED
    assert state.final_answer == "安装完成"
    assert len(handler.requests) == 1
    assert len(spy.calls) == 1
    assert len(llm.calls) == 2


def test_ask_deny_agent_loop_receives_observation(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    spy = SpyExecutionService(ws)
    handler = ScriptedPermissionHandler([PermissionDecision.DENY])
    registry = create_default_registry(
        workspace=ws,
        execution_service=spy,
        permission_handler=handler,
    )
    executor = ToolExecutor(registry)
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="run_command",
                        arguments={"command": "npm", "args": ["install"]},
                        arguments_raw='{"command":"npm","args":["install"]}',
                    ),
                ),
            ),
            LLMResponse(content="用户拒绝了安装，已停止。", tool_calls=()),
        ]
    )
    state = AgentLoop(llm, executor, registry, max_steps=5).run("try npm install")
    assert state.status == AgentStatus.COMPLETED
    assert state.termination_reason != "permission_required"
    assert spy.calls == []
    assert len(llm.calls) == 2
    roles = [m.role for m in state.conversation.messages]
    assert "tool" in roles
