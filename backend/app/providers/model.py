"""Model 领域对象（provider_id + model_id 唯一确定）。"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.providers.errors import InvalidModelError

#模型（供应商 id + 模型 id 唯一确定）
@dataclass(frozen=True)
class Model:
    """逻辑 Model 身份与能力声明。

    唯一键：``(provider_id, model_id)``。不含凭据。
    """

    provider_id: str
    model_id: str
    display_name: str
    context_window: int | None = None#上下文窗口
    supports_tool_call: bool = True#支持工具调用
    supports_streaming: bool = False#支持流式

    def __post_init__(self) -> None:
        pid = (self.provider_id or "").strip()
        mid = (self.model_id or "").strip()
        name = (self.display_name or "").strip()
        if not pid:
            raise InvalidModelError("provider_id 不能为空")
        if not mid:
            raise InvalidModelError("model_id 不能为空")
        if not name:
            raise InvalidModelError("display_name 不能为空")
        if self.context_window is not None and self.context_window <= 0:
            raise InvalidModelError("context_window 必须为正整数或 None")
        object.__setattr__(self, "provider_id", pid)
        object.__setattr__(self, "model_id", mid)
        object.__setattr__(self, "display_name", name)

    @property
    def key(self) -> tuple[str, str]:
        return (self.provider_id, self.model_id)
