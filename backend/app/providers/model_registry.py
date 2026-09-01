"""内存 ModelRegistry（不依赖数据库 / FastAPI / AgentLoop）。"""

from __future__ import annotations

from backend.app.providers.errors import (
    DuplicateModelError,
    InvalidModelError,
    ProviderModelMismatchError,
    UnknownModelError,
)
from backend.app.providers.model import Model


#根据供应商找支持的模型
class ModelRegistry:
    """按 (provider_id, model_id) 注册与查找 Model。"""

    def __init__(self) -> None:
        self._items: dict[tuple[str, str], Model] = {}

    def register(self, model: Model) -> None:
        if not isinstance(model, Model):
            raise InvalidModelError("register 需要 Model 实例")
        key = model.key
        if key in self._items:
            raise DuplicateModelError(
                f"Model 已注册: {model.provider_id}/{model.model_id}"
            )
        self._items[key] = model

    def get(self, provider_id: str, model_id: str) -> Model:
        pid = (provider_id or "").strip()
        mid = (model_id or "").strip()
        if not pid:
            raise InvalidModelError("provider_id 不能为空")
        if not mid:
            raise InvalidModelError("model_id 不能为空")

        # 若 model_id 存在于其他 provider，给出 mismatch；否则 unknown
        matches = [m for m in self._items.values() if m.model_id == mid]
        if matches and all(m.provider_id != pid for m in matches):
            owned = ", ".join(sorted({m.provider_id for m in matches}))
            raise ProviderModelMismatchError(
                f"Model {mid!r} 属于 provider [{owned}]，"
                f"与请求的 provider {pid!r} 不匹配"
            )

        key = (pid, mid)
        try:
            return self._items[key]
        except KeyError as exc:
            raise UnknownModelError(f"未知 Model: {pid}/{mid}") from exc

    def contains(self, provider_id: str, model_id: str) -> bool:
        pid = (provider_id or "").strip()
        mid = (model_id or "").strip()
        if not pid or not mid:
            return False
        return (pid, mid) in self._items

    def list(self) -> list[Model]:
        return [
            self._items[k]
            for k in sorted(self._items, key=lambda x: (x[0], x[1]))
        ]

    def list_for_provider(self, provider_id: str) -> list[Model]:
        pid = (provider_id or "").strip()
        if not pid:
            raise InvalidModelError("provider_id 不能为空")
        return [
            m
            for m in self.list()
            if m.provider_id == pid
        ]

    def __len__(self) -> int:
        return len(self._items)
