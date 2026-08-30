"""Provider / Model Domain + Registry + ModelResolver（V0.7）。

Phase 1：身份与目录。
Phase 2：ModelResolver 将 Session.provider_id/model_id 解析为 LLMClient。
"""

from __future__ import annotations

from backend.app.providers.credentials import CredentialSource, EnvCredentialSource
from backend.app.providers.defaults import (
    DEFAULT_MODEL_ID,
    DEFAULT_OPENAI_COMPAT_BASE_URL,
    DEFAULT_PROVIDER_ID,
    build_default_model_registry,
    build_default_provider_registry,
)
from backend.app.providers.errors import (
    DuplicateModelError,
    DuplicateProviderError,
    InvalidModelError,
    InvalidProviderError,
    ModelConfigurationError,
    ModelError,
    ProviderConfigurationError,
    ProviderError,
    ProviderModelMismatchError,
    UnknownModelError,
    UnknownProviderError,
)
from backend.app.providers.model import Model
from backend.app.providers.model_registry import ModelRegistry
from backend.app.providers.openai_compatible import (
    LLMClient,
    LLMConfig,
    build_openai_compatible_client,
)
from backend.app.providers.provider import Provider
from backend.app.providers.provider_registry import ProviderRegistry
from backend.app.providers.resolver import ModelResolver, ResolvedModel

__all__ = [
    "CredentialSource",
    "DEFAULT_MODEL_ID",
    "DEFAULT_OPENAI_COMPAT_BASE_URL",
    "DEFAULT_PROVIDER_ID",
    "DuplicateModelError",
    "DuplicateProviderError",
    "EnvCredentialSource",
    "InvalidModelError",
    "InvalidProviderError",
    "LLMClient",
    "LLMConfig",
    "Model",
    "ModelConfigurationError",
    "ModelError",
    "ModelRegistry",
    "ModelResolver",
    "Provider",
    "ProviderConfigurationError",
    "ProviderError",
    "ProviderModelMismatchError",
    "ProviderRegistry",
    "ResolvedModel",
    "UnknownModelError",
    "UnknownProviderError",
    "build_default_model_registry",
    "build_default_provider_registry",
    "build_openai_compatible_client",
]
