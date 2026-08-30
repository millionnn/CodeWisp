"""Provider / Model 领域错误（结构化、可测试）。"""

from __future__ import annotations

from backend.app.llm.errors import CodeWispError


class ProviderError(CodeWispError):
    """Provider 领域基础错误。"""

    code: str = "PROVIDER_ERROR"


class InvalidProviderError(ProviderError):
    """Provider 字段非法（如空 provider_id）。"""

    code = "INVALID_PROVIDER"


class DuplicateProviderError(ProviderError):
    """同一 provider_id 重复注册。"""

    code = "DUPLICATE_PROVIDER"


class UnknownProviderError(ProviderError):
    """Registry 中不存在该 provider_id。"""

    code = "UNKNOWN_PROVIDER"


class ProviderConfigurationError(ProviderError):
    """Provider 运行配置无效（凭据、能力、base_url 等）。"""

    code = "PROVIDER_CONFIGURATION_ERROR"


class ModelError(CodeWispError):
    """Model 领域基础错误。"""

    code: str = "MODEL_ERROR"


class InvalidModelError(ModelError):
    """Model 字段非法。"""

    code = "INVALID_MODEL"


class DuplicateModelError(ModelError):
    """同一 (provider_id, model_id) 重复注册。"""

    code = "DUPLICATE_MODEL"


class UnknownModelError(ModelError):
    """Registry 中不存在该 model。"""

    code = "UNKNOWN_MODEL"


class ProviderModelMismatchError(ModelError):
    """查询时 provider_id 与已注册 Model 的 provider 不一致。"""

    code = "MODEL_PROVIDER_MISMATCH"


class ModelConfigurationError(ModelError):
    """Model 运行配置无效。"""

    code = "MODEL_CONFIGURATION_ERROR"
