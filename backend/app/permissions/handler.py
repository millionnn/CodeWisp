"""PermissionHandler：用户授权抽象（CLI / 未来 Web / API）。"""

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
