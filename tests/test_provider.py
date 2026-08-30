"""Provider 领域对象测试。"""

from __future__ import annotations

import pytest

from backend.app.providers.defaults import (
    DEFAULT_MODEL_ID,
    DEFAULT_PROVIDER_ID,
    build_default_provider_registry,
)
from backend.app.providers.errors import InvalidProviderError
from backend.app.providers.provider import Provider
from backend.app.llm.client import DEFAULT_MODEL


def test_provider_creation() -> None:
    p = Provider(
        provider_id="deepseek",
        display_name="DeepSeek",
        capabilities=frozenset({"chat", "tool_call"}),
    )
    assert p.provider_id == "deepseek"
    assert p.display_name == "DeepSeek"
    assert p.has_capability("chat")
    assert not p.has_capability("vision")


def test_provider_strips_and_rejects_empty_id() -> None:
    p = Provider(provider_id="  openai  ", display_name="  OpenAI  ")
    assert p.provider_id == "openai"
    assert p.display_name == "OpenAI"
    with pytest.raises(InvalidProviderError):
        Provider(provider_id="  ", display_name="X")
    with pytest.raises(InvalidProviderError):
        Provider(provider_id="x", display_name="")


def test_provider_has_no_credential_fields() -> None:
    fields = set(Provider.__dataclass_fields__)
    assert "api_key" not in fields
    assert "secret" not in fields
    assert "credential" not in fields


def test_default_provider_ids_align_with_llm_defaults() -> None:
    assert DEFAULT_PROVIDER_ID == "deepseek"
    assert DEFAULT_MODEL_ID == DEFAULT_MODEL == "deepseek-chat"
    reg = build_default_provider_registry()
    assert reg.contains(DEFAULT_PROVIDER_ID)
    assert reg.contains("openai")
