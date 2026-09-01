"""LSP policy / failure tests."""

from __future__ import annotations

from backend.app.lsp.policy import LspPolicy, LspPolicyAction


def test_policy_allows_read_ops() -> None:
    policy = LspPolicy()
    for op in ("status", "diagnostics", "definition", "references", "symbols", "hover"):
        assert policy.decide(op).action is LspPolicyAction.ALLOW


def test_policy_denies_unknown() -> None:
    d = LspPolicy().decide("format_document")
    assert d.action is LspPolicyAction.DENY
