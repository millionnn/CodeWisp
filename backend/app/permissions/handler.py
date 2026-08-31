"""PermissionHandler：用户授权抽象（CLI / 未来 Web / API）。"""

#用户授权抽象（CLI / 未来 Web / API）
#决定怎么问用户

from __future__ import annotations

from typing import Protocol

from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.request import PermissionRequest


class PermissionHandler(Protocol):
    """Policy 判定 ASK 后，由 Handler 决定 ALLOW / DENY。"""

    def request(self, permission: PermissionRequest) -> PermissionDecision:
        """阻塞直到用户做出决定；不得自动 ALLOW。"""


class AlwaysDenyPermissionHandler:
    """测试 / 安全默认：一律 DENY。"""

    def request(self, permission: PermissionRequest) -> PermissionDecision:
        return PermissionDecision.DENY


class AlwaysAllowPermissionHandler:
    """API 显式 confirm 后使用：一律 ALLOW（仍须调用方先取得用户确认）。"""

    def request(self, permission: PermissionRequest) -> PermissionDecision:
        return PermissionDecision.ALLOW


class ScriptedPermissionHandler:
    """测试用：按队列返回预定决定。"""

    def __init__(self, decisions: list[PermissionDecision]) -> None:
        self._queue = list(decisions)
        self.requests: list[PermissionRequest] = []

    def request(self, permission: PermissionRequest) -> PermissionDecision:
        self.requests.append(permission)
        if not self._queue:
            return PermissionDecision.DENY
        return self._queue.pop(0)
