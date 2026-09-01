"""LSP policy — read-only code intelligence (always ALLOW)."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class LspPolicyAction(str, Enum):
    ALLOW = "allow"
    DENY = "deny"


@dataclass(frozen=True)
class LspPolicyDecision:
    action: LspPolicyAction
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"action": self.action.value, "reason": self.reason}


# Read-only operations
ALLOW_OPERATIONS: frozenset[str] = frozenset(
    {
        "status",
        "diagnostics",
        "definition",
        "references",
        "symbols",
        "hover",
    }
)


class LspPolicy:
    """LSP is read-only: no file mutation, no shell, no git."""

    def decide(self, operation: str) -> LspPolicyDecision:
        op = (operation or "").strip().lower()
        if op in ALLOW_OPERATIONS:
            return LspPolicyDecision(
                LspPolicyAction.ALLOW,
                f"LSP '{op}' is a read-only code intelligence operation.",
            )
        return LspPolicyDecision(
            LspPolicyAction.DENY,
            f"LSP operation '{op}' is not allowed.",
        )
