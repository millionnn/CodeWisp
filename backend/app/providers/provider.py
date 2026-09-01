"""Provider 领域对象（身份 + 能力，不含凭据）。"""

from __future__ import annotations

from dataclasses import dataclass

from backend.app.providers.errors import InvalidProviderError

#厂商对象（谁提供服务）
@dataclass(frozen=True)
class Provider:
    """逻辑 Provider 身份（如 deepseek / openai）。

    禁止携带 api_key / secret / credential。
    """

    provider_id: str
    display_name: str
    capabilities: frozenset[str] = frozenset()

    def __post_init__(self) -> None:
        pid = (self.provider_id or "").strip()
        if not pid:
            raise InvalidProviderError("provider_id 不能为空")
        name = (self.display_name or "").strip()
        if not name:
            raise InvalidProviderError("display_name 不能为空")
        caps = frozenset(str(c).strip() for c in self.capabilities if str(c).strip())
        object.__setattr__(self, "provider_id", pid)
        object.__setattr__(self, "display_name", name)
        object.__setattr__(self, "capabilities", caps)

    def has_capability(self, name: str) -> bool:
        return name in self.capabilities
