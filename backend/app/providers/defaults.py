"""默认 Provider / Model 身份（与 LLMConfig 默认值单一来源对齐）。

V0.7 Phase 2：ModelResolver 使用本目录将 Session 身份解析为 LLMClient。
"""

from __future__ import annotations

from backend.app.llm.client import DEFAULT_BASE_URL, DEFAULT_MODEL
from backend.app.providers.model import Model
from backend.app.providers.model_registry import ModelRegistry
from backend.app.providers.provider import Provider
from backend.app.providers.provider_registry import ProviderRegistry

# 与历史 Session / CLI 默认一致；模型名复用 LLMConfig 的 DEFAULT_MODEL，不另造第二套。
#默认用deepseek
DEFAULT_PROVIDER_ID = "deepseek"
DEFAULT_MODEL_ID = DEFAULT_MODEL  # deepseek-chat
DEFAULT_OPENAI_COMPAT_BASE_URL = DEFAULT_BASE_URL

# 硅基流动（OpenAI-compatible）
SILICONFLOW_PROVIDER_ID = "siliconflow"
SILICONFLOW_DEFAULT_BASE_URL = "https://api.siliconflow.cn/v1"
SILICONFLOW_DEFAULT_MODEL_ID = "Qwen/Qwen3.5-4B"

_CHAT_TOOL = frozenset({"chat", "tool_call", "openai_compatible"})

#构建默认供应商注册表
def build_default_provider_registry() -> ProviderRegistry:
    """内置 deepseek / openai / siliconflow 逻辑身份（无凭据）。"""
    registry = ProviderRegistry()
    registry.register(
        Provider(
            provider_id=DEFAULT_PROVIDER_ID,
            display_name="DeepSeek",
            capabilities=_CHAT_TOOL,
        )
    )
    #注册 openai 供应商
    registry.register(
        Provider(
            provider_id="openai",
            display_name="OpenAI",
            capabilities=_CHAT_TOOL,
        )
    )
    registry.register(
        Provider(
            provider_id=SILICONFLOW_PROVIDER_ID,
            display_name="SiliconFlow（硅基流动）",
            capabilities=_CHAT_TOOL,
        )
    )
    return registry

#构建默认模型注册表
def build_default_model_registry() -> ModelRegistry:
    """内置默认 Model 目录（身份 + 能力声明）。"""
    registry = ModelRegistry()
    registry.register(
        Model(
            provider_id=DEFAULT_PROVIDER_ID,
            model_id=DEFAULT_MODEL_ID,
            display_name="DeepSeek Chat",
            context_window=64_000,
            supports_tool_call=True,
            supports_streaming=False,
        )
    )
    # openai 身份：ModelResolver 可解析；凭据走 OPENAI_API_KEY 或 LLM_API_KEY。
    registry.register(
        Model(
            provider_id="openai",
            model_id="gpt-4o",
            display_name="GPT-4o",
            context_window=128_000,
            supports_tool_call=True,
            supports_streaming=False,
        )
    )
    registry.register(
        Model(
            provider_id="openai",
            model_id="gpt-4o-mini",
            display_name="GPT-4o mini",
            context_window=128_000,
            supports_tool_call=True,
            supports_streaming=False,
        )
    )
    registry.register(
        Model(
            provider_id=SILICONFLOW_PROVIDER_ID,
            model_id=SILICONFLOW_DEFAULT_MODEL_ID,
            display_name="Qwen3.5 4B (SiliconFlow)",
            context_window=32_768,
            supports_tool_call=True,
            supports_streaming=False,
        )
    )
    return registry
