"""ExecutionResult：语言无关的结构化执行结果。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

#结构化执行结果
@dataclass
class ExecutionResult:
    """一次命令执行的结果（与 ToolResult 分层）。"""

    success: bool#是否成功
    exit_code: int | None#退出码
    stdout: str#标准输出
    stderr: str#标准错误
    duration_ms: float#执行时间
    command: str#命令
    args: list[str] = field(default_factory=list)#参数
    cwd: str = "."#工作目录
    timed_out: bool = False
    truncated: bool = False#是否截断
    metadata: dict[str, Any] = field(default_factory=dict)#元数据

    def to_dict(self) -> dict[str, Any]:#将结果转换为字典
        return asdict(self)


@dataclass(frozen=True)
class PermissionRequired:
    """策略判定为 ASK：不执行命令，仅返回授权请求（供未来 Web UI）。"""

    command: str
    args: tuple[str, ...]
    cwd: str
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "permission_required": True,
            "command": self.command,
            "args": list(self.args),
            "cwd": self.cwd,
            "reason": self.reason,
        }
