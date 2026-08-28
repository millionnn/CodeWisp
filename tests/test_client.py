"""LLMClient 配置与错误处理测试（全部 mock，不使用真实 API Key）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from openai import APIConnectionError, APIError, AuthenticationError

from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import ConfigError, LLMNetworkError, LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse


def test_config_from_env_success(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-test-key")
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "demo-model")

    config = LLMConfig.from_env()
    assert config.api_key == "sk-test-key"
    assert config.base_url == "https://example.com/v1"
    assert config.model == "demo-model"


def test_config_missing_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.setenv("LLM_BASE_URL", "https://example.com/v1")
    monkeypatch.setenv("LLM_MODEL", "demo-model")

    with pytest.raises(ConfigError, match="LLM_API_KEY"):
        LLMConfig.from_env()


def test_config_empty_api_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "   ")
    with pytest.raises(ConfigError, match="LLM_API_KEY"):
        LLMConfig.from_env()


def test_config_empty_base_url(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.setenv("LLM_BASE_URL", "  ")
    with pytest.raises(ConfigError, match="LLM_BASE_URL"):
        LLMConfig.from_env()


def test_chat_success_with_mock() -> None:
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="pong", tool_calls=None),
                finish_reason="stop",
            )
        ]
    )

    config = LLMConfig(api_key="sk-test", base_url="https://example.com/v1", model="m")
    client = LLMClient(config, client=mock_openai)

    conv = Conversation()
    conv.add_user("ping")
    response = client.chat(conv)
    assert isinstance(response, LLMResponse)
    assert response.content == "pong"
    assert response.text == "pong"
    assert response.finish_reason == "stop"
    assert response.tool_calls == ()
    assert response.has_tool_calls is False
    assert response.raw_response is not None


def test_chat_maps_tool_calls_without_executing() -> None:
    """解析 tool_calls；Client 本身不执行工具。"""
    mock_openai = MagicMock()
    mock_tc = SimpleNamespace(
        id="call_1",
        function=SimpleNamespace(name="calculator", arguments='{"expression":"1+1"}'),
    )
    mock_openai.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None, tool_calls=[mock_tc]),
                finish_reason="tool_calls",
            )
        ]
    )

    config = LLMConfig(api_key="sk-test", base_url="https://example.com/v1", model="m")
    client = LLMClient(config, client=mock_openai)
    conv = Conversation()
    conv.add_user("算一下")
    response = client.chat(conv)

    assert response.content is None
    assert response.finish_reason == "tool_calls"
    assert len(response.tool_calls) == 1
    assert response.tool_calls[0].name == "calculator"
    assert response.tool_calls[0].arguments == {"expression": "1+1"}
    assert response.tool_calls[0].parse_error is None


def test_chat_malformed_tool_arguments_sets_parse_error() -> None:
    mock_openai = MagicMock()
    mock_tc = SimpleNamespace(
        id="call_bad",
        function=SimpleNamespace(name="calculator", arguments="{not-json"),
    )
    mock_openai.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=None, tool_calls=[mock_tc]),
                finish_reason="tool_calls",
            )
        ]
    )
    client = LLMClient(
        LLMConfig(api_key="sk", base_url="https://example.com/v1", model="m"),
        client=mock_openai,
    )
    conv = Conversation()
    conv.add_user("x")
    response = client.chat(conv)
    assert response.tool_calls[0].parse_error is not None
    assert response.tool_calls[0].arguments == {}


def test_chat_passes_tools_schema() -> None:
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.return_value = SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content="ok", tool_calls=None),
                finish_reason="stop",
            )
        ]
    )
    client = LLMClient(
        LLMConfig(api_key="sk", base_url="https://example.com/v1", model="m"),
        client=mock_openai,
    )
    conv = Conversation()
    conv.add_user("hi")
    tools = [{"type": "function", "function": {"name": "calculator", "parameters": {}}}]
    client.chat(conv, tools=tools)
    kwargs = mock_openai.chat.completions.create.call_args.kwargs
    assert kwargs["tools"] == tools
    assert kwargs["tool_choice"] == "auto"


def test_chat_auth_error() -> None:
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.side_effect = AuthenticationError(
        message="bad key",
        response=MagicMock(status_code=401, headers={}),
        body=None,
    )

    config = LLMConfig(api_key="bad", base_url="https://example.com/v1", model="m")
    client = LLMClient(config, client=mock_openai)
    conv = Conversation()
    conv.add_user("hi")

    with pytest.raises(LLMRequestError, match="鉴权"):
        client.chat(conv)


def test_chat_network_error() -> None:
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.side_effect = APIConnectionError(
        request=MagicMock()
    )

    config = LLMConfig(api_key="sk", base_url="https://example.com/v1", model="m")
    client = LLMClient(config, client=mock_openai)
    conv = Conversation()
    conv.add_user("hi")

    with pytest.raises(LLMNetworkError, match="网络|连接"):
        client.chat(conv)


def test_chat_api_error() -> None:
    mock_openai = MagicMock()
    mock_openai.chat.completions.create.side_effect = APIError(
        message="rate limited",
        request=MagicMock(),
        body=None,
    )

    config = LLMConfig(api_key="sk", base_url="https://example.com/v1", model="m")
    client = LLMClient(config, client=mock_openai)
    conv = Conversation()
    conv.add_user("hi")

    with pytest.raises(LLMRequestError, match="rate limited"):
        client.chat(conv)


def test_chat_empty_conversation() -> None:
    config = LLMConfig(api_key="sk", base_url="https://example.com/v1", model="m")
    client = LLMClient(config, client=MagicMock())
    with pytest.raises(ConfigError, match="对话为空"):
        client.chat(Conversation())
