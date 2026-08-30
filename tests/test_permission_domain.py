"""V0.8：Permission domain 单元测试。"""

from __future__ import annotations

import pytest

from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.errors import (
    InvalidPermissionDecisionError,
    PermissionInterruptedError,
)
from backend.app.permissions.handler import (
    AlwaysDenyPermissionHandler,
    ScriptedPermissionHandler,
)
from backend.app.permissions.request import PermissionRequest


def test_permission_request_serialization_roundtrip() -> None:
    req = PermissionRequest(
        command="npm",
        args=("install",),
        cwd="/tmp/ws",
        reason="ASK",
        tool_name="run_command",
        session_id="ses_1",
        agent_run_id="run_1",
    )
    data = req.to_dict()
    assert data["command"] == "npm"
    assert data["args"] == ["install"]
    restored = PermissionRequest.from_dict(data)
    assert restored.command == "npm"
    assert restored.args == ("install",)
    assert restored.request_id == req.request_id
    assert restored.session_id == "ses_1"


def test_permission_decision_allow_variants() -> None:
    for raw in ("y", "Y", "yes", "allow", "a"):
        assert PermissionDecision.parse(raw) is PermissionDecision.ALLOW


def test_permission_decision_deny_variants() -> None:
    for raw in ("n", "N", "no", "deny", "d"):
        assert PermissionDecision.parse(raw) is PermissionDecision.DENY


def test_permission_decision_invalid() -> None:
    with pytest.raises(InvalidPermissionDecisionError):
        PermissionDecision.parse("maybe")
    with pytest.raises(InvalidPermissionDecisionError):
        PermissionDecision.parse("")


def test_scripted_and_always_deny_handlers() -> None:
    req = PermissionRequest(command="pip", args=("install", "x"))
    scripted = ScriptedPermissionHandler(
        [PermissionDecision.ALLOW, PermissionDecision.DENY]
    )
    assert scripted.request(req) is PermissionDecision.ALLOW
    assert scripted.request(req) is PermissionDecision.DENY
    assert AlwaysDenyPermissionHandler().request(req) is PermissionDecision.DENY


def test_permission_interrupted_is_domain_error() -> None:
    err = PermissionInterruptedError("interrupted")
    assert "interrupted" in str(err)
