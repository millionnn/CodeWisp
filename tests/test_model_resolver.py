"""ModelResolver 单元测试（无真实 API）。"""

from __future__ import annotations

import pytest

from backend.app.llm.client import DEFAULT_BASE_URL, DEFAULT_MODEL, LLMClient, LLMConfig
from backend.app.providers.defaults import (
    DEFAULT_MODEL_ID,
    DEFAULT_PROVIDER_ID,
    build_default_model_registry,
    build_default_provider_registry,
)
from backend.app.providers.errors import (
    ModelConfigurationError,
    ProviderConfigurationError,
    ProviderModelMismatchError,
    UnknownModelError,
    UnknownProviderError,
)
from backend.app.providers.model import Model
from backend.app.providers.model_registry import ModelRegistry
from backend.app.providers.provider import Provider
from backend.app.providers.provider_registry import ProviderRegistry
from backend.app.providers.resolver import ModelResolver, ResolvedModel


def _fake_client(provider: Provider, model: Model, config: LLMConfig) -> LLMClient:
    client = LLMClient.__new__(LLMClient)
    client.config = config
    client._client = None  # type: ignore[attr-defined]
    return client


def test_resolve_deepseek(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    monkeypatch.delenv("LLM_BASE_URL", raising=False)
    resolver = ModelResolver.create_default(client_factory=_fake_client)
    resolved = resolver.resolve(DEFAULT_PROVIDER_ID, DEFAULT_MODEL_ID)
    assert isinstance(resolved, ResolvedModel)
    assert resolved.provider_id == "deepseek"
    assert resolved.model_id == "deepseek-chat"
    assert resolved.config.model == DEFAULT_MODEL == "deepseek-chat"
    assert resolved.config.base_url == DEFAULT_BASE_URL
    assert resolved.config.api_key == "sk-test"
    assert resolved.llm.config.model == "deepseek-chat"


def test_resolve_openai_uses_model_id(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-shared")
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    resolver = ModelResolver.create_default(client_factory=_fake_client)
    resolved = resolver.resolve("openai", "gpt-4o")
    assert resolved.provider_id == "openai"
    assert resolved.model_id == "gpt-4o"
    assert resolved.config.model == "gpt-4o"
    assert resolved.config.base_url == "https://api.openai.com/v1"


def test_unknown_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    resolver = ModelResolver.create_default(client_factory=_fake_client)
    with pytest.raises(UnknownProviderError) as exc:
        resolver.resolve("nope", "deepseek-chat")
    assert exc.value.code == "UNKNOWN_PROVIDER"


def test_unknown_model(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    resolver = ModelResolver.create_default(client_factory=_fake_client)
    with pytest.raises(UnknownModelError) as exc:
        resolver.resolve("deepseek", "no-such-model")
    assert exc.value.code == "UNKNOWN_MODEL"


def test_provider_model_mismatch(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    resolver = ModelResolver.create_default(client_factory=_fake_client)
    with pytest.raises(ProviderModelMismatchError) as exc:
        resolver.resolve("openai", "deepseek-chat")
    assert exc.value.code == "MODEL_PROVIDER_MISMATCH"


def test_provider_configuration_missing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    resolver = ModelResolver.create_default(client_factory=_fake_client)
    with pytest.raises(ProviderConfigurationError) as exc:
        resolver.resolve("deepseek", "deepseek-chat")
    assert exc.value.code == "PROVIDER_CONFIGURATION_ERROR"


def test_provider_without_openai_compatible_capability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    providers = ProviderRegistry()
    providers.register(
        Provider(
            provider_id="custom",
            display_name="Custom",
            capabilities=frozenset({"chat"}),
        )
    )
    models = ModelRegistry()
    models.register(
        Model(provider_id="custom", model_id="m1", display_name="M1")
    )
    resolver = ModelResolver(providers, models, client_factory=_fake_client)
    with pytest.raises(ProviderConfigurationError):
        resolver.resolve("custom", "m1")


def test_error_codes_stable() -> None:
    assert UnknownProviderError.code == "UNKNOWN_PROVIDER"
    assert UnknownModelError.code == "UNKNOWN_MODEL"
    assert ProviderModelMismatchError.code == "MODEL_PROVIDER_MISMATCH"
    assert ProviderConfigurationError.code == "PROVIDER_CONFIGURATION_ERROR"
    assert ModelConfigurationError.code == "MODEL_CONFIGURATION_ERROR"


def test_resolve_siliconflow_ignores_deepseek_base_url(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """即使 LLM_BASE_URL 指向 DeepSeek，siliconflow 也必须用自己的默认 endpoint。"""
    monkeypatch.setenv("SILICONFLOW_API_KEY", "sk-sf")
    monkeypatch.setenv("LLM_BASE_URL", "https://api.deepseek.com")
    monkeypatch.delenv("SILICONFLOW_BASE_URL", raising=False)
    resolver = ModelResolver.create_default(client_factory=_fake_client)
    resolved = resolver.resolve("siliconflow", "Qwen/Qwen3.5-4B")
    assert resolved.config.base_url == "https://api.siliconflow.cn/v1"
    assert resolved.config.model == "Qwen/Qwen3.5-4B"
