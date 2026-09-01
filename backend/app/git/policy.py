"""GitPolicy — structured ALLOW / ASK / DENY for Git operations."""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


# Git操作权限
class GitPolicyAction(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True)
class GitPolicyDecision:
    action: GitPolicyAction
    reason: str
    subcommand: str = ""

    def to_dict(self) -> dict[str, str]:
        data = {"action": self.action.value, "reason": self.reason}
        if self.subcommand:
            data["subcommand"] = self.subcommand
        return data


# Read-only subcommands — default ALLOW
ALLOW_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "status",
        "diff",
        "log",
        "show",
        "branch",
        "rev-parse",
        "ls-files",
        "describe",
        "tag",
        "remote",
        "config",
        "help",
        "version",
    }
)

# Mutating subcommands — default ASK
ASK_SUBCOMMANDS: frozenset[str] = frozenset(
    {
        "add",
        "commit",
        "checkout",
        "switch",
        "merge",
        "rebase",
        "cherry-pick",
        "stash",
        "reset",
        "restore",
        "clean",
        "push",
        "pull",
        "fetch",
        "mv",
        "rm",
    }
)


class GitPolicy:
    """Parse git subcommand + flags into structured policy decisions."""

    def decide(self, subcommand: str, args: tuple[str, ...] | list[str] = ()) -> GitPolicyDecision:
        sub = (subcommand or "").strip().lower()
        if not sub:
            return GitPolicyDecision(
                GitPolicyAction.DENY,
                "Git 子命令为空，拒绝执行。",
            )

        tokens = [str(a) for a in args]

        # High-risk combinations — DENY regardless of subcommand
        deny = self._check_deny_flags(sub, tokens)
        if deny is not None:
            return deny

        if sub in ALLOW_SUBCOMMANDS:
            return GitPolicyDecision(
                GitPolicyAction.ALLOW,
                f"git {sub} 为只读操作，允许执行。",
                subcommand=sub,
            )

        if sub in ASK_SUBCOMMANDS:
            return GitPolicyDecision(
                GitPolicyAction.ASK,
                f"git {sub} 可能改变仓库状态，需要用户授权。",
                subcommand=sub,
            )

        return GitPolicyDecision(
            GitPolicyAction.DENY,
            f"git {sub} 不在允许列表中，拒绝执行。",
            subcommand=sub,
        )

    def _check_deny_flags(
        self, subcommand: str, tokens: list[str]
    ) -> GitPolicyDecision | None:
        flag_set = set(tokens)
        joined = " ".join(tokens).lower()

        # git push --force / -f
        if subcommand == "push":
            if "--force" in flag_set or "-f" in flag_set or "--force-with-lease" in flag_set:
                return GitPolicyDecision(
                    GitPolicyAction.DENY,
                    "git push --force 为高风险操作，默认禁止。",
                    subcommand=subcommand,
                )

        # git reset --hard
        if subcommand == "reset":
            if "--hard" in flag_set:
                return GitPolicyDecision(
                    GitPolicyAction.DENY,
                    "git reset --hard 为破坏性操作，默认禁止。",
                    subcommand=subcommand,
                )

        # git clean -fd / -fdx
        if subcommand == "clean":
            for t in tokens:
                if t.startswith("-") and "f" in t and ("d" in t or "x" in t):
                    return GitPolicyDecision(
                        GitPolicyAction.DENY,
                        "git clean -fd/-fdx 为破坏性操作，默认禁止。",
                        subcommand=subcommand,
                    )

        # git branch -D
        if subcommand == "branch":
            if "-D" in flag_set or "--delete" in flag_set and "--force" in flag_set:
                return GitPolicyDecision(
                    GitPolicyAction.DENY,
                    "git branch -D 为破坏性操作，默认禁止。",
                    subcommand=subcommand,
                )
            if "-D" in flag_set:
                return GitPolicyDecision(
                    GitPolicyAction.DENY,
                    "git branch -D 为破坏性操作，默认禁止。",
                    subcommand=subcommand,
                )

        # git checkout -- .
        if subcommand in {"checkout", "restore"}:
            if "--" in tokens:
                idx = tokens.index("--")
                rest = tokens[idx + 1 :]
                if "." in rest or any(r.endswith("/.") for r in rest):
                    return GitPolicyDecision(
                        GitPolicyAction.DENY,
                        "git checkout -- . 为破坏性操作，默认禁止。",
                        subcommand=subcommand,
                    )

        # git reset --hard via combined flags
        if subcommand == "reset" and "hard" in joined:
            return GitPolicyDecision(
                GitPolicyAction.DENY,
                "git reset --hard 为破坏性操作，默认禁止。",
                subcommand=subcommand,
            )

        return None
