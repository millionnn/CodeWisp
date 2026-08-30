"""ModelRegistry 测试。"""

from __future__ import annotations

import pytest

from backend.app.llm.client import DEFAULT_MODEL, LLMConfig
from backend.app.providers.defaults import (
    DEFAULT_MODEL_ID,
    DEFAULT_PROVIDER_ID,
    build_default_model_registry,
    build_default_provider_registry,
)
from backend.app.providers.errors import (
    DuplicateModelError,
    InvalidModelError,
    ProviderModelMismatchError,
    UnknownModelError,
)
from backend.app.providers.model import Model
from backend.app.providers.model_registry import ModelRegistry
from backend.app.providers.openai_compatible import build_openai_compatible_client


def test_register_get_list_for_provider() -> None:
    reg = ModelRegistry()
    reg.register(
        Model(
            provider_id="deepseek",
            model_id="deepseek-chat",
            display_name="Chat",
        )
    )
    reg.register(
        Model(provider_id="openai", model_id="gpt-4o", display_name="4o")
    )
    assert reg.contains("deepseek", "deepseek-chat")
    assert reg.get("deepseek", "deepseek-chat").display_name == "Chat"
    assert [m.model_id for m in reg.list_for_provider("deepseek")] == [
        "deepseek-chat"
    ]
    assert len(reg.list()) == 2


def test_duplicate_model() -> None:
    reg = ModelRegistry()
    m = Model(
        provider_id="deepseek",
        model_id="deepseek-chat",
        display_name="Chat",
    )
    reg.register(m)
    with pytest.raises(DuplicateModelError):
        reg.register(
            Model(
                provider_id="deepseek",
                model_id="deepseek-chat",
                display_name="Other",
            )
        )


def test_unknown_model() -> None:
    reg = ModelRegistry()
    with pytest.raises(UnknownModelError):
        reg.get("deepseek", "nope")


def test_provider_mismatch() -> None:
    reg = ModelRegistry()
    reg.register(
        Model(
            provider_id="deepseek",
            model_id="deepseek-chat",
            display_name="Chat",
        )
    )
    with pytest.raises(ProviderModelMismatchError):
        reg.get("openai", "deepseek-chat")


def test_list_for_provider_empty_id() -> None:
    reg = ModelRegistry()
    with pytest.raises(InvalidModelError):
        reg.list_for_provider("")


def test_registry_isolation() -> None:
    a = ModelRegistry()
    b = ModelRegistry()
    a.register(
        Model(
            provider_id="deepseek",
            model_id="deepseek-chat",
            display_name="Chat",
        )
    )
    assert not b.contains("deepseek", "deepseek-chat")


def test_default_model_registry_backward_compatible() -> None:
    """deepseek / deepseek-chat 与 LLMConfig 默认一致，且可被 Registry 解析。"""
    assert DEFAULT_MODEL_ID == DEFAULT_MODEL
    providers = build_default_provider_registry()
    models = build_default_model_registry()
    assert providers.contains(DEFAULT_PROVIDER_ID)
    m = models.get(DEFAULT_PROVIDER_ID, DEFAULT_MODEL_ID)
    assert m.model_id == "deepseek-chat"
    assert m.supports_tool_call is True


def test_openai_compatible_client_uses_llmconfig(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    monkeypatch.delenv("LLM_MODEL", raising=False)
    client = build_openai_compatible_client()
    assert client.config.model == DEFAULT_MODEL
    assert isinstance(client.config, LLMConfig)
