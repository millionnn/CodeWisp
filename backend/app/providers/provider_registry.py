"""内存 ProviderRegistry（不依赖 SQLite / FastAPI / AgentLoop）。"""

from __future__ import annotations

from backend.app.providers.errors import (
    DuplicateProviderError,
    InvalidProviderError,
    UnknownProviderError,
)
from backend.app.providers.provider import Provider

#注册本agent支持的llm的供应商
class ProviderRegistry:
    """按 provider_id 注册与查找 Provider。"""

    def __init__(self) -> None:
        self._items: dict[str, Provider] = {}

    #注册供应商
    def register(self, provider: Provider) -> None:
        if not isinstance(provider, Provider):
            raise InvalidProviderError("register 需要 Provider 实例")
        if provider.provider_id in self._items:
            raise DuplicateProviderError(
                f"Provider 已注册: {provider.provider_id}"
            )
        self._items[provider.provider_id] = provider

    #根据供应商 id 获取供应商
    def get(self, provider_id: str) -> Provider:
        pid = (provider_id or "").strip()
        if not pid:
            raise InvalidProviderError("provider_id 不能为空")
        try:
            return self._items[pid]
        except KeyError as exc:
            raise UnknownProviderError(f"未知 Provider: {pid}") from exc

    #判断供应商是否注册
    def contains(self, provider_id: str) -> bool:
        pid = (provider_id or "").strip()
        if not pid:
            return False
        return pid in self._items

    #获取所有供应商
    def list(self) -> list[Provider]:
        return [self._items[k] for k in sorted(self._items)]

    def __len__(self) -> int:
        return len(self._items)
