"""CommandPolicy 单元测试。"""

from __future__ import annotations

from backend.app.execution.policy import CommandPolicy, PolicyAction
from backend.app.execution.request import ExecutionRequest


def _decide(command: str, *args: str):
    return CommandPolicy().decide(ExecutionRequest(command=command, args=list(args)))


def test_allow_common_dev_commands() -> None:
    for cmd in ("pytest", "python", "python3", "npm", "mvn", "cargo", "go", "git"):
        d = _decide(cmd, "test")
        # git test 不是真实子命令，但政策层只看 basename + ask 规则
        if cmd == "git" and "test" not in {
            "reset",
            "push",
            "clean",
            "commit",
            "rebase",
            "merge",
            "checkout",
            "add",
        }:
            assert d.action is PolicyAction.ALLOW
        elif cmd != "git":
            assert d.action is PolicyAction.ALLOW, cmd


def test_allow_python_path_basename() -> None:
    d = _decide("/usr/bin/python3", "-c", "print(1)")
    assert d.action is PolicyAction.ALLOW


def test_allow_case_insensitive() -> None:
    assert _decide("PyTest", "tests").action is PolicyAction.ALLOW


def test_ask_npm_install() -> None:
    d = _decide("npm", "install")
    assert d.action is PolicyAction.ASK
    assert "授权" in d.reason or "install" in d.reason.lower()


def test_ask_git_push() -> None:
    assert _decide("git", "push", "origin", "main").action is PolicyAction.ASK


def test_ask_pip_install() -> None:
    assert _decide("pip", "install", "requests").action is PolicyAction.ASK


def test_deny_sudo() -> None:
    d = _decide("sudo", "ls")
    assert d.action is PolicyAction.DENY


def test_deny_rm() -> None:
    assert _decide("rm", "-rf", "/").action is PolicyAction.DENY


def test_deny_shell() -> None:
    assert _decide("bash", "-c", "echo hi").action is PolicyAction.DENY
    assert _decide("sh", "-c", "echo hi").action is PolicyAction.DENY


def test_deny_empty_command() -> None:
    assert _decide("").action is PolicyAction.DENY


def test_deny_unknown_command() -> None:
    assert _decide("curl", "https://example.com").action is PolicyAction.DENY


def test_git_status_allow() -> None:
    assert _decide("git", "status").action is PolicyAction.ALLOW


def test_decision_to_dict() -> None:
    d = _decide("pytest")
    data = d.to_dict()
    assert data["action"] == "allow"
    assert "reason" in data
