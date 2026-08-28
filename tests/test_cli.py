"""CLI 输入处理测试（mock Agent / LLM，无真实网络）。"""

from __future__ import annotations

from typing import Any

from backend.app.agent.loop import AgentLoop
from backend.app.cli.interface import EXIT_COMMANDS, run_cli
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry


class ScriptedLLMClient(LLMClient):
    """按队列返回预设 LLMResponse。"""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.config = LLMConfig(api_key="fake", base_url="http://localhost", model="fake")
        self._client = None  # type: ignore[assignment]
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        conversation: Conversation,
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {"messages": conversation.to_api_messages(), "tools": tools}
        )
        if not self._responses:
            raise LLMRequestError("脚本响应已用尽")
        return self._responses.pop(0)


def _make_agent(responses: list[LLMResponse], *, max_steps: int = 10) -> AgentLoop:
    registry = create_default_registry()
    return AgentLoop(
        ScriptedLLMClient(responses),
        ToolExecutor(registry),
        registry,
        max_steps=max_steps,
    )


def test_cli_multi_turn_and_history() -> None:
    agent = _make_agent(
        [
            LLMResponse(content="echo:hello", finish_reason="stop"),
            LLMResponse(content="echo:trees", finish_reason="stop"),
        ]
    )
    inputs = iter(["hello", "what about trees?", "/exit"])
    outputs: list[str] = []

    code = run_cli(
        agent,
        input_fn=lambda _prompt: next(inputs),
        output_fn=outputs.append,
        show_tool_trace=False,
    )

    assert code == 0
    assert any("CodeWisp:" in line for line in outputs)
    assert any("echo:hello" in line for line in outputs)
    assert any("echo:trees" in line for line in outputs)


def test_cli_empty_input_ignored() -> None:
    agent = _make_agent([])
    inputs = iter(["", "  ", "/quit"])
    outputs: list[str] = []

    code = run_cli(
        agent,
        input_fn=lambda _prompt: next(inputs),
        output_fn=outputs.append,
    )

    assert code == 0
    assert any("空输入" in line for line in outputs)


def test_cli_eof_exits_cleanly() -> None:
    agent = _make_agent([])
    outputs: list[str] = []

    code = run_cli(
        agent,
        input_fn=lambda _prompt: None,
        output_fn=outputs.append,
    )

    assert code == 0
    assert any("再见" in line for line in outputs)


def test_cli_shows_tool_trace_and_answer() -> None:
    agent = _make_agent(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="calculator",
                        arguments={"expression": "2+2"},
                        arguments_raw='{"expression":"2+2"}',
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="答案是 4", finish_reason="stop"),
        ]
    )
    inputs = iter(["算 2+2", "/exit"])
    outputs: list[str] = []

    code = run_cli(
        agent,
        input_fn=lambda _prompt: next(inputs),
        output_fn=outputs.append,
        show_tool_trace=True,
    )

    assert code == 0
    assert any("[工具] calculator" in line for line in outputs)
    assert any("答案是 4" in line for line in outputs)


def test_exit_commands_recognized() -> None:
    assert "exit" in EXIT_COMMANDS
    assert "/quit" in EXIT_COMMANDS
