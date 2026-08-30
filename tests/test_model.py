"""Model 领域对象测试。"""

from __future__ import annotations

import pytest

from backend.app.providers.defaults import DEFAULT_MODEL_ID, DEFAULT_PROVIDER_ID
from backend.app.providers.errors import InvalidModelError
from backend.app.providers.model import Model


def test_model_creation() -> None:
    m = Model(
        provider_id="deepseek",
        model_id="deepseek-chat",
        display_name="DeepSeek Chat",
        context_window=64_000,
        supports_tool_call=True,
        supports_streaming=False,
    )
    assert m.key == ("deepseek", "deepseek-chat")
    assert m.supports_tool_call is True
    assert m.context_window == 64_000


def test_model_validation() -> None:
    with pytest.raises(InvalidModelError):
        Model(provider_id="", model_id="m", display_name="n")
    with pytest.raises(InvalidModelError):
        Model(provider_id="p", model_id="", display_name="n")
    with pytest.raises(InvalidModelError):
        Model(provider_id="p", model_id="m", display_name="")
    with pytest.raises(InvalidModelError):
        Model(
            provider_id="p",
            model_id="m",
            display_name="n",
            context_window=0,
        )


def test_model_strips_ids() -> None:
    m = Model(
        provider_id="  deepseek ",
        model_id=" deepseek-chat ",
        display_name=" Chat ",
    )
    assert m.provider_id == "deepseek"
    assert m.model_id == "deepseek-chat"
    assert m.display_name == "Chat"


def test_default_model_identity() -> None:
    m = Model(
        provider_id=DEFAULT_PROVIDER_ID,
        model_id=DEFAULT_MODEL_ID,
        display_name="DeepSeek Chat",
    )
    assert m.provider_id == "deepseek"
    assert m.model_id == "deepseek-chat"


def test_model_has_no_credential_fields() -> None:
    fields = set(Model.__dataclass_fields__)
    assert "api_key" not in fields
