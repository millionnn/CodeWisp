"""V0.8：CliPermissionHandler 交互测试。"""

from __future__ import annotations

import pytest

from backend.app.permissions.cli import CliPermissionHandler
from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.errors import PermissionInterruptedError
from backend.app.permissions.request import PermissionRequest


def _req() -> PermissionRequest:
    return PermissionRequest(
        command="npm",
        args=("install",),
        cwd="/workspace",
        reason="Package install requires approval.",
    )


def test_cli_permission_y_allow() -> None:
    lines: list[str] = []
    handler = CliPermissionHandler(
        input_fn=lambda _p: "y",
        output_fn=lines.append,
    )
    assert handler.request(_req()) is PermissionDecision.ALLOW
    blob = "\n".join(lines)
    assert "Permission required" in blob
    assert "npm install" in blob


def test_cli_permission_yes_allow() -> None:
    handler = CliPermissionHandler(
        input_fn=lambda _p: "yes",
        output_fn=lambda _s: None,
    )
    assert handler.request(_req()) is PermissionDecision.ALLOW


def test_cli_permission_n_deny() -> None:
    handler = CliPermissionHandler(
        input_fn=lambda _p: "n",
        output_fn=lambda _s: None,
    )
    assert handler.request(_req()) is PermissionDecision.DENY


def test_cli_permission_no_deny() -> None:
    handler = CliPermissionHandler(
        input_fn=lambda _p: "no",
        output_fn=lambda _s: None,
    )
    assert handler.request(_req()) is PermissionDecision.DENY


def test_cli_permission_invalid_then_allow() -> None:
    answers = iter(["maybe", "y"])
    lines: list[str] = []
    handler = CliPermissionHandler(
        input_fn=lambda _p: next(answers),
        output_fn=lines.append,
    )
    assert handler.request(_req()) is PermissionDecision.ALLOW
    assert any("y/yes" in line or "无效" in line for line in lines)


def test_cli_permission_eof_raises() -> None:
    handler = CliPermissionHandler(
        input_fn=lambda _p: None,
        output_fn=lambda _s: None,
    )
    with pytest.raises(PermissionInterruptedError):
        handler.request(_req())


def test_cli_permission_keyboard_interrupt() -> None:
    def boom(_prompt: str) -> str | None:
        raise KeyboardInterrupt

    handler = CliPermissionHandler(input_fn=boom, output_fn=lambda _s: None)
    with pytest.raises(PermissionInterruptedError):
        handler.request(_req())
