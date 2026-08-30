"""PendingPermissionBroker：供 FastAPI / 未来 Web UI 异步提交决定。"""

from __future__ import annotations

import threading
from dataclasses import dataclass

from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.errors import PermissionError, PermissionInterruptedError
from backend.app.permissions.request import PermissionRequest


@dataclass
class _PendingSlot:
    request: PermissionRequest
    event: threading.Event
    decision: PermissionDecision | None = None
    cancelled: bool = False


class PendingPermissionBroker:
    """按 session 挂起一个待授权请求，供 HTTP decide 唤醒。"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._pending: dict[str, _PendingSlot] = {}

    def get_pending(self, session_id: str) -> PermissionRequest | None:
        with self._lock:
            slot = self._pending.get(session_id)
            return slot.request if slot is not None else None

    def submit_and_wait(
        self,
        permission: PermissionRequest,
        *,
        timeout: float | None = None,
    ) -> PermissionDecision:
        session_id = permission.session_id or ""
        if not session_id:
            raise PermissionError("PermissionRequest.session_id 不能为空（API broker）")
        slot = _PendingSlot(request=permission, event=threading.Event())
        with self._lock:
            if session_id in self._pending:
                raise PermissionError(f"Session 已有待处理授权: {session_id}")
            self._pending[session_id] = slot
        try:
            ok = slot.event.wait(timeout=timeout)
            if not ok:
                raise PermissionInterruptedError("等待授权超时")
            if slot.cancelled or slot.decision is None:
                raise PermissionInterruptedError("授权等待被取消")
            return slot.decision
        finally:
            with self._lock:
                self._pending.pop(session_id, None)

    def decide(
        self,
        session_id: str,
        *,
        request_id: str,
        decision: PermissionDecision,
    ) -> PermissionRequest:
        with self._lock:
            slot = self._pending.get(session_id)
            if slot is None:
                raise PermissionError(f"没有待处理授权: {session_id}")
            if slot.request.request_id != request_id:
                raise PermissionError(
                    f"request_id 不匹配: expected {slot.request.request_id}"
                )
            slot.decision = decision
            slot.event.set()
            return slot.request

    def cancel(self, session_id: str) -> None:
        with self._lock:
            slot = self._pending.get(session_id)
            if slot is None:
                return
            slot.cancelled = True
            slot.event.set()


class BrokerPermissionHandler:
    """Web/API：阻塞在 Broker 上直到 decide。"""

    def __init__(self, broker: PendingPermissionBroker, *, timeout: float | None = 600) -> None:
        self._broker = broker
        self._timeout = timeout

    def request(self, permission: PermissionRequest) -> PermissionDecision:
        return self._broker.submit_and_wait(permission, timeout=self._timeout)
