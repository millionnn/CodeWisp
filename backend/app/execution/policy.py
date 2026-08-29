"""CommandPolicy：显式 ALLOW / ASK / DENY（为未来 Permission UI 留接口）。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from backend.app.execution.request import ExecutionRequest


class PolicyAction(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True)
class ExecutionDecision:
    """策略判定结果。"""

    action: PolicyAction
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"action": self.action.value, "reason": self.reason}


# 默认可尝试的开发/测试命令（basename，大小写不敏感）
DEFAULT_ALLOWLIST: frozenset[str] = frozenset(
    {
        "pytest",
        "python",
        "python3",
        "npm",
        "node",
        "npx",
        "mvn",
        "gradle",
        "gradlew",
        "go",
        "cargo",
        "cmake",
        "make",
        "ctest",
        "git",
    }
)

# 明显危险：一律拒绝
DEFAULT_DENYLIST: frozenset[str] = frozenset(
    {
        "sudo",
        "rm",
        "rmdir",
        "shutdown",
        "reboot",
        "mkfs",
        "dd",
        "bash",
        "sh",
        "zsh",
        "fish",
        "csh",
        "dash",
        "cmd",
        "powershell",
        "pwsh",
    }
)

# (command, frozenset of first-arg subcommands) → ASK
DEFAULT_ASK_SUBCOMMANDS: dict[str, frozenset[str]] = {
    "npm": frozenset({"install", "ci", "uninstall", "update"}),
    "npx": frozenset({"--yes"}),  # 少见；主要靠 npm
    "pip": frozenset({"install", "uninstall"}),
    "pip3": frozenset({"install", "uninstall"}),
    "yarn": frozenset({"add", "install", "upgrade"}),
    "pnpm": frozenset({"add", "install", "update"}),
    "git": frozenset(
        {"reset", "push", "clean", "commit", "rebase", "merge", "checkout", "add"}
    ),
}


class CommandPolicy:
    """基于 allow/ask/deny 规则的命令策略（与具体语言无关）。"""

    def __init__(
        self,
        *,
        allowlist: frozenset[str] | None = None,
        denylist: frozenset[str] | None = None,
        ask_subcommands: dict[str, frozenset[str]] | None = None,
    ) -> None:
        self._allowlist = {
            c.lower() for c in (allowlist if allowlist is not None else DEFAULT_ALLOWLIST)
        }
        self._denylist = {
            c.lower() for c in (denylist if denylist is not None else DEFAULT_DENYLIST)
        }
        raw_ask = (
            ask_subcommands
            if ask_subcommands is not None
            else DEFAULT_ASK_SUBCOMMANDS
        )
        self._ask_subcommands = {
            cmd.lower(): {s.lower() for s in subs} for cmd, subs in raw_ask.items()
        }

    def decide(self, request: ExecutionRequest) -> ExecutionDecision:
        basename = _command_basename(request.command)
        if not basename:
            return ExecutionDecision(
                PolicyAction.DENY,
                "command 为空，拒绝执行。",
            )

        if basename in self._denylist:
            return ExecutionDecision(
                PolicyAction.DENY,
                f"命令 '{basename}' 在拒绝列表中，禁止执行。",
            )

        first = _first_arg(request.args)
        ask_subs = self._ask_subcommands.get(basename)
        if ask_subs is not None and first is not None and first in ask_subs:
            return ExecutionDecision(
                PolicyAction.ASK,
                f"命令 '{basename} {first}' 可能改变仓库或环境状态，需要用户授权后才能执行。",
            )

        # pip 本身不在默认 allowlist，但 pip install 已由 ASK 覆盖；
        # 其它 pip 子命令若未列入则 DENY（未知）。
        if basename in self._allowlist:
            return ExecutionDecision(
                PolicyAction.ALLOW,
                f"命令 '{basename}' 在开发命令允许列表中。",
            )

        return ExecutionDecision(
            PolicyAction.DENY,
            f"命令 '{basename}' 不在允许列表中，拒绝执行。",
        )


def _command_basename(command: str) -> str:
    text = (command or "").strip()
    if not text:
        return ""
    # 支持绝对/相对路径形式的解释器，如 /usr/bin/python3
    name = Path(text).name
    # Windows: python.exe
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name.lower()


def _first_arg(args: tuple[str, ...] | list[str]) -> str | None:
    for raw in args:
        token = str(raw).strip()
        if not token or token.startswith("-"):
            continue
        return token.lower()
    return None
