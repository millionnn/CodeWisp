"""PermissionDecision：用户对 ASK 的最终决定。"""

#对于ask的回答：是否允许执行这条命令

from __future__ import annotations

from enum import Enum

from backend.app.permissions.errors import InvalidPermissionDecisionError


class PermissionDecision(str, Enum):
    ALLOW = "allow"#允许
    DENY = "deny"#拒绝

    @classmethod
    def parse(cls, raw: str | None) -> PermissionDecision:
        #解析用户输入的决策
        text = (raw or "").strip().lower()
        if text in {"y", "yes", "allow", "a"}:
            return cls.ALLOW
        if text in {"n", "no", "deny", "d"}:
            return cls.DENY
        raise InvalidPermissionDecisionError(
            f"无效决定: {raw!r}（请输入 y/yes 或 n/no）"
        )
