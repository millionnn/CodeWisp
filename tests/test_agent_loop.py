"""AgentLoop 单元测试（全部脚本化 LLM，不调用真实 API）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.app.agent.loop import AgentLoop
from backend.app.agent.state import AgentStatus
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.tools.base import Tool
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry
from backend.app.tools.registry import ToolRegistry
from backend.app.tools.result import ToolResult


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


class AlwaysFailTool(Tool):
    @property
    def name(self) -> str:
        return "always_fail"

    @property
    def description(self) -> str:
        return "always fails"

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    def execute(self, arguments: dict[str, Any]) -> ToolResult:
        return ToolResult(success=False, output=None, error="故意失败")


def _agent(
    responses: list[LLMResponse],
    *,
    max_steps: int = 10,
    registry: ToolRegistry | None = None,
) -> tuple[AgentLoop, ScriptedLLMClient]:
    reg = registry or create_default_registry()
    llm = ScriptedLLMClient(responses)
    loop = AgentLoop(llm, ToolExecutor(reg), reg, max_steps=max_steps)
    return loop, llm


def _calc_call(expression: str, call_id: str = "call_1") -> ToolCall:
    raw = f'{{"expression":"{expression}"}}'
    return ToolCall(
        id=call_id,
        name="calculator",
        arguments={"expression": expression},
        arguments_raw=raw,
    )


def test_final_answer_without_tool_call() -> None:
    loop, llm = _agent([LLMResponse(content="你好", finish_reason="stop")])
    state = loop.run("打个招呼")
    assert state.status == AgentStatus.COMPLETED
    assert state.termination_reason == "completed"
    assert state.final_answer == "你好"
    assert state.step == 1
    assert llm.calls[0]["tools"]  # schema 已传给模型


def test_single_calculator_tool_call_and_observation() -> None:
    loop, llm = _agent(
        [
            LLMResponse(
                content=None,
                tool_calls=(_calc_call("123 * 456"),),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="123 × 456 = 56088", finish_reason="stop"),
        ]
    )
    state = loop.run("计算 123 * 456")
    assert state.status == AgentStatus.COMPLETED
    assert state.final_answer == "123 × 456 = 56088"
    assert state.step == 2

    # 第二次 LLM 调用应看到 tool observation
    second_msgs = llm.calls[1]["messages"]
    roles = [m["role"] for m in second_msgs]
    assert "tool" in roles
    tool_msg = next(m for m in second_msgs if m["role"] == "tool")
    assert "56088" in tool_msg["content"]


def test_multi_step_tool_calls() -> None:
    loop, llm = _agent(
        [
            LLMResponse(
                content=None,
                tool_calls=(_calc_call("123 * 456", "c1"),),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="c2",
                        name="get_current_time",
                        arguments={},
                        arguments_raw="{}",
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="乘积是 56088，时间见上。", finish_reason="stop"),
        ]
    )
    state = loop.run("计算 123*456 并告诉我时间")
    assert state.status == AgentStatus.COMPLETED
    assert state.step == 3
    assert len(llm.calls) == 3
    event_types = [e.event_type for e in state.events]
    assert event_types.count("tool_completed") == 2


def test_multiple_tool_calls_in_one_response() -> None:
    loop, _llm = _agent(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    _calc_call("2+2", "a"),
                    ToolCall(
                        id="b",
                        name="get_current_time",
                        arguments={},
                        arguments_raw="{}",
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="都完成了", finish_reason="stop"),
        ]
    )
    state = loop.run("算一下并看时间")
    assert state.status == AgentStatus.COMPLETED
    assert sum(1 for e in state.events if e.event_type == "tool_completed") == 2


def test_unknown_tool_becomes_observation_not_crash() -> None:
    loop, llm = _agent(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="x",
                        name="no_such_tool",
                        arguments={},
                        arguments_raw="{}",
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="工具不存在，我改用文字回答。", finish_reason="stop"),
        ]
    )
    state = loop.run("调用不存在的工具")
    assert state.status == AgentStatus.COMPLETED
    tool_msg = next(m for m in llm.calls[1]["messages"] if m["role"] == "tool")
    assert "未找到" in tool_msg["content"] or "success\": false" in tool_msg["content"]


def test_invalid_arguments_observation() -> None:
    loop, llm = _agent(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="x",
                        name="calculator",
                        arguments={},  # 缺少 expression
                        arguments_raw="{}",
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="参数有误", finish_reason="stop"),
        ]
    )
    state = loop.run("坏参数")
    assert state.status == AgentStatus.COMPLETED
    tool_msg = next(m for m in llm.calls[1]["messages"] if m["role"] == "tool")
    assert "缺少必需参数" in tool_msg["content"]


def test_malformed_json_arguments() -> None:
    loop, llm = _agent(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="x",
                        name="calculator",
                        arguments={},
                        arguments_raw="{bad",
                        parse_error="JSON 解析失败：Expecting property name",
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="JSON 坏了", finish_reason="stop"),
        ]
    )
    state = loop.run("坏 JSON")
    assert state.status == AgentStatus.COMPLETED
    tool_msg = next(m for m in llm.calls[1]["messages"] if m["role"] == "tool")
    assert "非法" in tool_msg["content"] or "JSON" in tool_msg["content"]


def test_tool_execution_failure_observation() -> None:
    registry = ToolRegistry()
    registry.register(AlwaysFailTool())
    loop, llm = _agent(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(id="x", name="always_fail", arguments={}, arguments_raw="{}"),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="工具失败了我知道了", finish_reason="stop"),
        ],
        registry=registry,
    )
    state = loop.run("失败工具")
    assert state.status == AgentStatus.COMPLETED
    tool_msg = next(m for m in llm.calls[1]["messages"] if m["role"] == "tool")
    assert "故意失败" in tool_msg["content"]


def test_llm_failure_sets_failed() -> None:
    loop, _ = _agent([])  # 队列空 → LLMRequestError
    # 放一个会在 chat 时失败的 client：空队列
    state = loop.run("任意")
    assert state.status == AgentStatus.FAILED
    assert state.error is not None


def test_max_steps() -> None:
    forever = LLMResponse(
        content=None,
        tool_calls=(_calc_call("1+1", "loop"),),
        finish_reason="tool_calls",
    )
    loop, _ = _agent([forever, forever, forever], max_steps=2)
    state = loop.run("无限工具")
    assert state.status == AgentStatus.MAX_STEPS
    assert state.termination_reason == "max_steps"
    assert state.step == 2
    assert "最大步数" in (state.error or "")


def test_empty_task_failed() -> None:
    loop, _ = _agent([])
    state = loop.run("   ")
    assert state.status == AgentStatus.FAILED
    assert state.termination_reason == "failed"


def test_permission_required_hard_stops_loop(tmp_path: Path) -> None:
    """ASK / permission_required：写入 observation 后硬停，不再调用 LLM。"""
    from backend.app.workspace.workspace import Workspace

    registry = create_default_registry(workspace=Workspace(tmp_path))
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="p1",
                        name="run_command",
                        arguments={"command": "npm", "args": ["install"]},
                        arguments_raw="{}",
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="不应执行", finish_reason="stop"),
        ]
    )
    loop = AgentLoop(llm, ToolExecutor(registry), registry, max_steps=5)
    state = loop.run("安装依赖")
    assert state.status == AgentStatus.PERMISSION_REQUIRED
    assert state.termination_reason == "permission_required"
    assert len(llm.calls) == 1


def test_initial_status_idle_on_fresh_state_object() -> None:
    from backend.app.agent.state import AgentState

    assert AgentState().status == AgentStatus.IDLE


def test_events_include_lifecycle() -> None:
    loop, _ = _agent([LLMResponse(content="done", finish_reason="stop")])
    state = loop.run("x")
    types = [e.event_type for e in state.events]
    assert types[0] == "agent_started"
    assert "llm_called" in types
    assert types[-1] == "agent_completed"


def test_loop_rejects_final_answer_while_plan_open(tmp_path: Path) -> None:
    """Plan 未逐步完成时，不得提前输出最终回答。"""
    from backend.app.context.budget import ContextBudget
    from backend.app.context.manager import DefaultContextManager
    from backend.app.persistence.context_repository import ContextRepository
    from backend.app.persistence.store import SqliteStore
    from backend.app.session.service import SessionService

    store = SqliteStore(tmp_path / "plan_loop.db")
    store.connect()
    session = SessionService(store).create_session(workspace=str(tmp_path), title="p")
    cm = DefaultContextManager(
        session_id=session.session_id,
        workspace_root=str(tmp_path),
        budget=ContextBudget.from_context_window(32_000),
        repository=ContextRepository(store),
    )
    cm.begin_run("修复 bug", agent_run_id=None)

    loop, llm = _agent(
        [
            LLMResponse(content="我已经全部修好了。", finish_reason="stop"),
            LLMResponse(content="我继续做当前步骤。", finish_reason="stop"),
        ],
        max_steps=2,
    )
    loop.context_manager = cm
    state = loop.run("修 bug")
    assert len(llm.calls) == 2
    assert state.final_answer != "我已经全部修好了。"
    nudge_msgs = [m for m in llm.calls[1]["messages"] if m["role"] == "user"]
    assert any("Plan 尚未逐步完成" in m["content"] for m in nudge_msgs)
    assert cm.plan_has_open_steps()
