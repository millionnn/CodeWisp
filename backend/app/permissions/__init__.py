"""Permission domain（V0.8）：Policy ASK → Handler ALLOW/DENY。"""

from __future__ import annotations

from backend.app.permissions.broker import BrokerPermissionHandler, PendingPermissionBroker
from backend.app.permissions.cli import CliPermissionHandler
from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.errors import (
    InvalidPermissionDecisionError,
    PermissionError,
    PermissionInterruptedError,
)
from backend.app.permissions.handler import (
    AlwaysDenyPermissionHandler,
    PermissionHandler,
    ScriptedPermissionHandler,
)
from backend.app.permissions.request import PermissionRequest, new_permission_request_id

__all__ = [
    "AlwaysDenyPermissionHandler",
    "BrokerPermissionHandler",
    "CliPermissionHandler",
    "InvalidPermissionDecisionError",
    "PendingPermissionBroker",
    "PermissionDecision",
    "PermissionError",
    "PermissionHandler",
    "PermissionInterruptedError",
    "PermissionRequest",
    "ScriptedPermissionHandler",
    "new_permission_request_id",
]
