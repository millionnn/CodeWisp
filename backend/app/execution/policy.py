"""CommandPolicy：显式 ALLOW / ASK / DENY（为未来 Permission UI 留接口）。"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

from backend.app.execution.request import ExecutionRequest

#策略动作
class PolicyAction(str, Enum):
    ALLOW = "allow"#允许
    ASK = "ask"#询问
    DENY = "deny"#拒绝


#执行决策
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

# 明显危险：一律拒绝（删除类改为 ASK，见 DEFAULT_ASK_COMMANDS）
DEFAULT_DENYLIST: frozenset[str] = frozenset(
    {
        "sudo",
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

# 整命令一律 ASK（任意参数），例如删除文件需用户确认
DEFAULT_ASK_COMMANDS: frozenset[str] = frozenset(
    {
        "rm",
        "rmdir",
        "unlink",
    }
)

# (command, frozenset of first-arg subcommands) → ASK
DEFAULT_ASK_SUBCOMMANDS: dict[str, frozenset[str]] = {
    # npm：含常用缩写 i（install）
    "npm": frozenset(
        {"install", "i", "ci", "uninstall", "un", "update", "add", "remove", "rm"}
    ),
    "npx": frozenset({"--yes"}),  # 少见；主要靠 npm
    "pip": frozenset({"install", "uninstall"}),
    "pip3": frozenset({"install", "uninstall"}),
    "yarn": frozenset({"add", "install", "upgrade", "remove"}),
    "pnpm": frozenset({"add", "install", "i", "update", "remove", "rm"}),
    "git": frozenset(
        {"reset", "push", "clean", "commit", "rebase", "merge", "checkout", "add"}
    ),
}


#命令策略
class CommandPolicy:
    """基于 allow/ask/deny 规则的命令策略（与具体语言无关）。"""

    def __init__(
        self,
        *,
        allowlist: frozenset[str] | None = None,
        denylist: frozenset[str] | None = None,
        ask_commands: frozenset[str] | None = None,
        ask_subcommands: dict[str, frozenset[str]] | None = None,
    ) -> None:
        #初始化
        self._allowlist = {
            c.lower() for c in (allowlist if allowlist is not None else DEFAULT_ALLOWLIST)
        }
        self._denylist = {
            c.lower() for c in (denylist if denylist is not None else DEFAULT_DENYLIST)
        }
        self._ask_commands = {
            c.lower()
            for c in (ask_commands if ask_commands is not None else DEFAULT_ASK_COMMANDS)
        }
        #初始化询问子命令
        raw_ask = (
            ask_subcommands
            if ask_subcommands is not None
            else DEFAULT_ASK_SUBCOMMANDS
        )
        self._ask_subcommands = {
            cmd.lower(): {s.lower() for s in subs} for cmd, subs in raw_ask.items()
        }

    #决策执行
    def decide(self, request: ExecutionRequest) -> ExecutionDecision:
        #获取命令基名
        basename = _command_basename(request.command)
        if not basename:
            return ExecutionDecision(
                PolicyAction.DENY,
                "command 为空，拒绝执行。",
            )

        #检查拒绝列表
        if basename in self._denylist:
            return ExecutionDecision(
                PolicyAction.DENY,
                f"命令 '{basename}' 在拒绝列表中，禁止执行。",
            )

        # 整命令 ASK（如 rm）：任意参数都需授权，不可落入 allowlist
        if basename in self._ask_commands:
            return ExecutionDecision(
                PolicyAction.ASK,
                f"命令 '{basename}' 可能删除或破坏文件，需要用户授权后才能执行。",
            )

        #获取第一个参数
        first = _first_arg(request.args)
        #获取询问子命令
        ask_subs = self._ask_subcommands.get(basename)
        #如果询问子命令不为空，并且第一个参数不为空，并且第一个参数在询问子命令中
        if ask_subs is not None and first is not None and first in ask_subs:
            #返回询问决策
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

#获取命令基名
def _command_basename(command: str) -> str:
    text = (command or "").strip()
    if not text:
        return ""
    # 支持绝对/相对路径形式的解释器，如 /usr/bin/python3（获取文件名）
    name = Path(text).name
    # Windows: python.exe（去掉.exe后缀）
    if name.lower().endswith(".exe"):
        name = name[:-4]
    return name.lower()

#获取第一个参数
def _first_arg(args: tuple[str, ...] | list[str]) -> str | None:
    for raw in args:
        token = str(raw).strip()
        if not token or token.startswith("-"):
            continue
        return token.lower()
    return None
