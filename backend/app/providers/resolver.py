"""ModelResolver：Session.provider_id/model_id → Provider/Model → LLMClient。

AgentLoop 不参与 resolution；Provider 特判只允许出现在本层 / OpenAI-compatible 适配层。
"""
#解析使用的供应商和模型
from __future__ import annotations

import os
from collections.abc import Callable
from dataclasses import dataclass

from backend.app.llm.client import DEFAULT_BASE_URL, LLMClient, LLMConfig
from backend.app.llm.errors import ConfigError
from backend.app.providers.credentials import CredentialSource, EnvCredentialSource
from backend.app.providers.defaults import (
    DEFAULT_MODEL_ID,
    DEFAULT_PROVIDER_ID,
    SILICONFLOW_DEFAULT_BASE_URL,
    SILICONFLOW_PROVIDER_ID,
    build_default_model_registry,
    build_default_provider_registry,
)
from backend.app.providers.errors import (
    ModelConfigurationError,
    ProviderConfigurationError,
)
from backend.app.providers.model import Model
from backend.app.providers.model_registry import ModelRegistry
from backend.app.providers.provider import Provider
from backend.app.providers.provider_registry import ProviderRegistry

# OpenAI-compatible 适配：按 provider 查默认 base_url / 凭据环境变量（非 AgentLoop 分支）
_DEFAULT_BASE_URLS: dict[str, str] = {
    DEFAULT_PROVIDER_ID: DEFAULT_BASE_URL,
    "openai": "https://api.openai.com/v1",
    SILICONFLOW_PROVIDER_ID: SILICONFLOW_DEFAULT_BASE_URL,
}
_BASE_URL_ENV_VARS: dict[str, tuple[str, ...]] = {
    DEFAULT_PROVIDER_ID: ("LLM_BASE_URL",),
    "openai": ("OPENAI_BASE_URL",),
    # 禁止回退 LLM_BASE_URL：否则会把 Qwen 请求打到 DeepSeek 域名
    SILICONFLOW_PROVIDER_ID: ("SILICONFLOW_BASE_URL",),
}
_API_KEY_ENV_VARS: dict[str, tuple[str, ...]] = {
    DEFAULT_PROVIDER_ID: ("LLM_API_KEY",),
    "openai": ("OPENAI_API_KEY", "LLM_API_KEY"),
    SILICONFLOW_PROVIDER_ID: ("SILICONFLOW_API_KEY", "LLM_API_KEY"),
}

ClientFactory = Callable[[Provider, Model, LLMConfig], LLMClient]

#解析结果：供应商、模型、配置、客户端
@dataclass(frozen=True)
class ResolvedModel:
    """一次 resolve 的结果：领域身份 + 可注入 AgentLoop 的 LLM 客户端。"""

    provider: Provider
    model: Model
    config: LLMConfig
    llm: LLMClient

    @property
    def provider_id(self) -> str:
        return self.provider.provider_id

    @property
    def model_id(self) -> str:
        return self.model.model_id


class ModelResolver:
    """将 provider_id + model_id 解析为 ResolvedModel。"""

    def __init__(
        self,
        providers: ProviderRegistry,
        models: ModelRegistry,
        *,
        credentials: CredentialSource | None = None,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._providers = providers
        self._models = models
        self._credentials = credentials or EnvCredentialSource()
        self._client_factory = client_factory

    @classmethod
    def create_default(
        cls,
        *,
        credentials: CredentialSource | None = None,
        client_factory: ClientFactory | None = None,
    ) -> ModelResolver:
        return cls(
            build_default_provider_registry(),
            build_default_model_registry(),
            credentials=credentials,
            client_factory=client_factory,
        )

    def resolve(self, provider_id: str, model_id: str) -> ResolvedModel:
        provider, model = self.lookup(provider_id, model_id)

        #判断供应商是否支持 openai_compatible runtime
        if "openai_compatible" not in provider.capabilities:
            raise ProviderConfigurationError(
                f"Provider {provider.provider_id!r} 不支持 openai_compatible runtime"
            )

        config = self._build_openai_compatible_config(provider, model)
        if self._client_factory is not None:
            llm = self._client_factory(provider, model, config)
        else:
            llm = LLMClient(config)
        return ResolvedModel(provider=provider, model=model, config=config, llm=llm)

    def lookup(self, provider_id: str, model_id: str) -> tuple[Provider, Model]:
        """仅查 Registry（不建 Client、不读凭据）。供 CLI 切换模型前校验。"""
        provider = self._providers.get(provider_id)
        model = self._models.get(provider.provider_id, model_id)
        if model.provider_id != provider.provider_id:
            raise ModelConfigurationError(
                f"Model {model.model_id!r} 不属于 Provider {provider.provider_id!r}"
            )
        return provider, model

    def find_models_by_id(self, model_id: str) -> list[Model]:
        mid = (model_id or "").strip()
        if not mid:
            return []
        return [m for m in self._models.list() if m.model_id == mid]

    @property
    def providers(self) -> ProviderRegistry:
        return self._providers

    @property
    def models(self) -> ModelRegistry:
        return self._models

    def is_credential_configured(self, provider_id: str) -> bool:
        """环境变量中是否已配置 key（不验证 key 是否有效）。"""
        for env_name in _API_KEY_ENV_VARS.get(provider_id, ("LLM_API_KEY",)):
            if (os.getenv(env_name) or "").strip():
                return True
        try:
            self._credentials.get_api_key()
            return True
        except ConfigError:
            return False

    #构建 openai 兼容的配置
    def _build_openai_compatible_config(        self,
        provider: Provider,
        model: Model,
    ) -> LLMConfig:
        try:
            api_key = self._api_key_for(provider.provider_id)
        except ConfigError as exc:
            raise ProviderConfigurationError(str(exc)) from exc

        base_url = self._base_url_for(provider.provider_id)
        if not base_url:
            raise ProviderConfigurationError(
                f"Provider {provider.provider_id!r} 缺少有效 base_url"
            )
        mid = (model.model_id or "").strip()
        if not mid:
            raise ModelConfigurationError("resolved model_id 为空")

        return LLMConfig(api_key=api_key, base_url=base_url, model=mid)

    #获取 api key
    def _api_key_for(self, provider_id: str) -> str:
        for env_name in _API_KEY_ENV_VARS.get(provider_id, ("LLM_API_KEY",)):
            value = (os.getenv(env_name) or "").strip()
            if value:
                return value
        # 回退到注入的 CredentialSource（默认读 LLM_API_KEY）
        return self._credentials.get_api_key()

    #获取 base url
    def _base_url_for(self, provider_id: str) -> str:
        for env_name in _BASE_URL_ENV_VARS.get(provider_id, ("LLM_BASE_URL",)):
            value = (os.getenv(env_name) or "").strip()
            if value:
                return value
        return _DEFAULT_BASE_URLS.get(provider_id, DEFAULT_BASE_URL)


__all__ = [
    "ClientFactory",
    "DEFAULT_MODEL_ID",
    "DEFAULT_PROVIDER_ID",
    "ModelResolver",
    "ResolvedModel",
]
