"""CLI 输入处理测试（mock LLM，无真实网络）。"""

from __future__ import annotations

from backend.app.cli.interface import EXIT_COMMANDS, run_cli
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse


class FakeLLMClient(LLMClient):
    """确定性替身：回声用户文本，并记录每次请求的历史长度。"""

    def __init__(self) -> None:
        # 绕过真实 OpenAI 客户端构造。
        self.config = LLMConfig(api_key="fake", base_url="http://localhost", model="fake")
        self._client = None  # type: ignore[assignment]
        self.calls: list[list[dict[str, str]]] = []

    def chat(self, conversation: Conversation) -> LLMResponse:
        self.calls.append(conversation.to_api_messages())
        last_user = next(
            (m.content for m in reversed(conversation.messages) if m.role == "user"),
            "",
        )
        return LLMResponse(content=f"echo:{last_user}", finish_reason="stop")


class FailingLLMClient(FakeLLMClient):
    def chat(self, conversation: Conversation) -> LLMResponse:
        raise LLMRequestError("模拟失败")


def test_cli_multi_turn_and_history() -> None:
    client = FakeLLMClient()
    inputs = iter(["hello", "what about trees?", "/exit"])
    outputs: list[str] = []

    code = run_cli(
        client,
        input_fn=lambda _prompt: next(inputs),
        output_fn=outputs.append,
    )

    assert code == 0
    assert len(client.calls) == 2
    # 第二次调用必须携带上一轮 user + assistant。
    second = client.calls[1]
    roles = [m["role"] for m in second]
    assert roles.count("user") == 2
    assert roles.count("assistant") == 1
    assert any("CodeWisp:" in line for line in outputs)
    assert any("echo:hello" in line for line in outputs)


def test_cli_empty_input_ignored() -> None:
    client = FakeLLMClient()
    inputs = iter(["", "  ", "/quit"])
    outputs: list[str] = []

    code = run_cli(
        client,
        input_fn=lambda _prompt: next(inputs),
        output_fn=outputs.append,
    )

    assert code == 0
    assert client.calls == []
    assert any("空输入" in line for line in outputs)


def test_cli_eof_exits_cleanly() -> None:
    client = FakeLLMClient()
    outputs: list[str] = []

    code = run_cli(
        client,
        input_fn=lambda _prompt: None,
        output_fn=outputs.append,
    )

    assert code == 0
    assert any("再见" in line for line in outputs)


def test_cli_llm_error_does_not_pollute_history() -> None:
    client = FailingLLMClient()
    inputs = iter(["boom", "/exit"])
    outputs: list[str] = []

    code = run_cli(
        client,
        input_fn=lambda _prompt: next(inputs),
        output_fn=outputs.append,
    )

    assert code == 0
    assert any("错误：模拟失败" in line for line in outputs)


def test_exit_commands_recognized() -> None:
    assert "exit" in EXIT_COMMANDS
    assert "/quit" in EXIT_COMMANDS
