"""V0.4-C：AgentLoop + run_command 集成测试（脚本化 LLM）。"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from backend.app.agent.loop import AgentLoop
from backend.app.agent.state import AgentStatus
from backend.app.execution.policy import CommandPolicy
from backend.app.execution.request import ExecutionRequest
from backend.app.execution.result import ExecutionResult
from backend.app.execution.service import ExecutionService
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
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
        return super().run(request)


def test_agent_run_command_then_answer(tmp_path: Path) -> None:
    """用户：运行命令并告诉我结果。Fake LLM：run_command → final。"""
    workspace = Workspace(tmp_path)
    spy = SpyExecutionService(workspace)
    registry = create_default_registry(workspace=workspace, execution_service=spy)
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="1",
                        name="run_command",
                        arguments={
                            "command": sys.executable,
                            "args": ["-c", "print('suite-ok')"],
                            "timeout": 10,
                        },
                        arguments_raw="{}",
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content="测试输出为 suite-ok，命令成功。",
                finish_reason="stop",
            ),
        ]
    )
    agent = AgentLoop(llm, ToolExecutor(registry), registry)
    state = agent.run("运行测试并告诉我结果。")

    assert state.status == AgentStatus.COMPLETED
    assert state.final_answer and "suite-ok" in state.final_answer
    assert len(spy.calls) == 1
    tool_names = [e.tool_name for e in state.events if e.event_type == "tool_completed"]
    assert tool_names == ["run_command"]

    schema_names = {
        t["function"]["name"] for t in (llm.calls[0]["tools"] or []) if "function" in t
    }
    assert "run_command" in schema_names


def test_agent_permission_required_no_execute(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    spy = SpyExecutionService(workspace)
    registry = create_default_registry(
        workspace=workspace,
        execution_service=spy,
        command_policy=CommandPolicy(),
    )
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="1",
                        name="run_command",
                        arguments={"command": "git", "args": ["push"]},
                        arguments_raw="{}",
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content="该命令需要用户授权（permission_required），本次未执行。",
                finish_reason="stop",
            ),
        ]
    )
    agent = AgentLoop(llm, ToolExecutor(registry), registry)
    state = agent.run("请 git push")

    assert state.status == AgentStatus.COMPLETED
    assert spy.calls == []
    failed = [e for e in state.events if e.event_type == "tool_failed"]
    assert len(failed) == 1
    meta = failed[0].metadata
    # ToolExecutor 把 ToolResult.to_dict() 放进 event metadata
    assert meta.get("output", {}).get("permission_required") is True or meta.get(
        "metadata", {}
    ).get("permission_required") is True


def test_agent_nonzero_exit_as_observation(tmp_path: Path) -> None:
    workspace = Workspace(tmp_path)
    registry = create_default_registry(workspace=workspace)
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="1",
                        name="run_command",
                        arguments={
                            "command": sys.executable,
                            "args": ["-c", "raise SystemExit(2)"],
                            "timeout": 10,
                        },
                        arguments_raw="{}",
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content="命令以退出码 2 失败，但 Agent 未崩溃。",
                finish_reason="stop",
            ),
        ]
    )
    agent = AgentLoop(llm, ToolExecutor(registry), registry)
    state = agent.run("运行一个会失败的命令")
    assert state.status == AgentStatus.COMPLETED
    assert any(e.event_type == "tool_failed" for e in state.events)
