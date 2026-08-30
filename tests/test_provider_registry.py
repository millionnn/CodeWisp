"""ProviderRegistry 测试。"""

from __future__ import annotations

import pytest

from backend.app.providers.defaults import (
    DEFAULT_PROVIDER_ID,
    build_default_provider_registry,
)
from backend.app.providers.errors import (
    DuplicateProviderError,
    InvalidProviderError,
    UnknownProviderError,
)
from backend.app.providers.provider import Provider
from backend.app.providers.provider_registry import ProviderRegistry


def test_register_get_contains_list() -> None:
    reg = ProviderRegistry()
    reg.register(Provider(provider_id="deepseek", display_name="DeepSeek"))
    assert reg.contains("deepseek")
    assert not reg.contains("openai")
    assert reg.get("deepseek").display_name == "DeepSeek"
    assert [p.provider_id for p in reg.list()] == ["deepseek"]


def test_duplicate_registration() -> None:
    reg = ProviderRegistry()
    reg.register(Provider(provider_id="deepseek", display_name="A"))
    with pytest.raises(DuplicateProviderError):
        reg.register(Provider(provider_id="deepseek", display_name="B"))


def test_unknown_provider() -> None:
    reg = ProviderRegistry()
    with pytest.raises(UnknownProviderError):
        reg.get("missing")


def test_empty_provider_id_rejected() -> None:
    reg = ProviderRegistry()
    with pytest.raises(InvalidProviderError):
        reg.get("")
    with pytest.raises(InvalidProviderError):
        reg.get("   ")


def test_registry_isolation() -> None:
    a = ProviderRegistry()
    b = ProviderRegistry()
    a.register(Provider(provider_id="deepseek", display_name="A"))
    assert not b.contains("deepseek")
    assert len(a) == 1
    assert len(b) == 0


def test_default_registry_has_deepseek() -> None:
    reg = build_default_provider_registry()
    assert reg.get(DEFAULT_PROVIDER_ID).provider_id == "deepseek"
    ids = {p.provider_id for p in reg.list()}
    assert ids == {"deepseek", "openai", "siliconflow"}
