"""OpenAI-compatible Provider Runtime 边界。

```text
Session.provider_id / model_id
        ↓
ModelResolver（Phase 2）
        ↓
LLMConfig + EnvCredentialSource
        ↓
LLMClient (openai SDK)
        ↓
AgentLoop(llm=...)
```

本模块**不推翻**既有 ``LLMClient`` / ``LLMConfig``。
AgentLoop 禁止出现 ``if provider == "deepseek"``；Provider 适配逻辑在 Resolver 层。
"""

from __future__ import annotations

from backend.app.llm.client import (
    DEFAULT_BASE_URL,
    DEFAULT_MODEL,
    LLMClient,
    LLMConfig,
)
from backend.app.providers.credentials import EnvCredentialSource

__all__ = [
    "DEFAULT_BASE_URL",
    "DEFAULT_MODEL",
    "EnvCredentialSource",
    "LLMClient",
    "LLMConfig",
    "build_openai_compatible_client",
]

#构建 openai 兼容的客户端
def build_openai_compatible_client(
    config: LLMConfig | None = None,
    *,
    credentials: EnvCredentialSource | None = None,
) -> LLMClient:
    """构造 OpenAI 兼容 LLMClient。

    - 均缺省：``LLMConfig.from_env()``（与 V0.6 行为一致）
    - 仅 ``credentials``：api_key 来自 CredentialSource；base_url/model 仍读 env 默认

    Phase 2：优先使用 ModelResolver 按 Session 解析；本函数仍可用于显式构造。
    """
    import os
    #如果 config 和 credentials 都为空，则使用默认配置
    if config is None and credentials is None:
        return LLMClient(LLMConfig.from_env())
    #如果 config 为空，则使用 credentials 构建 config
    if config is None:
        assert credentials is not None
        base_url = (os.getenv("LLM_BASE_URL") or DEFAULT_BASE_URL).strip()
        model = (os.getenv("LLM_MODEL") or DEFAULT_MODEL).strip()
        config = LLMConfig(
            api_key=credentials.get_api_key(),
            base_url=base_url or DEFAULT_BASE_URL,
            model=model or DEFAULT_MODEL,
        )
    elif credentials is not None:
        config = LLMConfig(
            api_key=credentials.get_api_key(),
            base_url=config.base_url,
            model=config.model,
        )
    return LLMClient(config)
