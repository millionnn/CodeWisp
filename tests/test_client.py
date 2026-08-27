"""LLMClient 配置与错误处理测试（全部 mock，不使用真实 API Key）。"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from openai import APIConnectionError, APIError, AuthenticationError

from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import ConfigError, LLMNetworkError, LLMRequestError
from backend.app.llm.messages import Conversation


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
        choices=[SimpleNamespace(message=SimpleNamespace(content="pong"))]
    )

    config = LLMConfig(api_key="sk-test", base_url="https://example.com/v1", model="m")
    client = LLMClient(config, client=mock_openai)

    conv = Conversation()
    conv.add_user("ping")
    assert client.chat(conv) == "pong"


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
