"""GitPolicy tests."""

from __future__ import annotations

from backend.app.git.policy import GitPolicy, GitPolicyAction


def test_allow_read_commands() -> None:
    policy = GitPolicy()
    for sub in ("status", "diff", "log", "show", "branch", "rev-parse"):
        d = policy.decide(sub)
        assert d.action is GitPolicyAction.ALLOW, sub


def test_ask_mutating_commands() -> None:
    policy = GitPolicy()
    for sub in ("add", "commit", "checkout", "push", "reset", "clean"):
        d = policy.decide(sub)
        assert d.action is GitPolicyAction.ASK, sub


def test_deny_force_push() -> None:
    d = GitPolicy().decide("push", ["--force", "origin", "main"])
    assert d.action is GitPolicyAction.DENY


def test_deny_reset_hard() -> None:
    d = GitPolicy().decide("reset", ["--hard", "HEAD"])
    assert d.action is GitPolicyAction.DENY


def test_deny_clean_fd() -> None:
    d = GitPolicy().decide("clean", ["-fd"])
    assert d.action is GitPolicyAction.DENY


def test_deny_branch_force_delete() -> None:
    d = GitPolicy().decide("branch", ["-D", "feature"])
    assert d.action is GitPolicyAction.DENY


def test_deny_checkout_dot() -> None:
    d = GitPolicy().decide("checkout", ["--", "."])
    assert d.action is GitPolicyAction.DENY
