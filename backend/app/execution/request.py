"""ExecutionRequest：语言无关的结构化执行请求。"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Mapping

from backend.app.execution.errors import InvalidExecutionRequestError

DEFAULT_TIMEOUT_SECONDS = 30.0#默认超时时间
MAX_TIMEOUT_SECONDS = 120.0#最大超时时间
MIN_TIMEOUT_SECONDS = 0.1#最小超时时间


@dataclass(frozen=True)
class ExecutionRequest:
    """一次受控命令执行的输入。

    command 与 args 分离，禁止拼成 shell 字符串。
    cwd 相对（或落在）Workspace，由 ExecutionService 再 resolve。
    """

    command: str
    args: tuple[str, ...] = ()
    cwd: str = "."
    timeout: float = DEFAULT_TIMEOUT_SECONDS
    env: Mapping[str, str] | None = None

#初始化，规范化字段
    def __post_init__(self) -> None:
        # frozen dataclass：用 object.__setattr__ 规范化字段
        cmd = (self.command or "").strip()
        object.__setattr__(self, "command", cmd)

        if isinstance(self.args, list):
            object.__setattr__(self, "args", tuple(str(a) for a in self.args))
        else:
            object.__setattr__(self, "args", tuple(str(a) for a in self.args))

        cwd = "." if self.cwd is None or str(self.cwd).strip() == "" else str(self.cwd)
        object.__setattr__(self, "cwd", cwd)

        try:
            timeout = float(self.timeout)
        except (TypeError, ValueError) as exc:
            raise InvalidExecutionRequestError("timeout 必须为数字。") from exc
        object.__setattr__(self, "timeout", timeout)

        if self.env is not None:
            object.__setattr__(
                self,
                "env",
                {str(k): str(v) for k, v in dict(self.env).items()},
            )

#校验请求
    def validate(self) -> None:
        """校验请求；非法时抛出 InvalidExecutionRequestError。"""
        if not self.command:
            raise InvalidExecutionRequestError("command 不能为空。")
        if self.timeout < MIN_TIMEOUT_SECONDS:
            raise InvalidExecutionRequestError(
                f"timeout 过小（最小 {MIN_TIMEOUT_SECONDS}s）。"
            )
        if self.timeout > MAX_TIMEOUT_SECONDS:
            raise InvalidExecutionRequestError(
                f"timeout 超过上限（最大 {MAX_TIMEOUT_SECONDS}s）。"
            )

#将请求转换为列表
    def argv(self) -> list[str]:
        """返回 subprocess 用的 [command, *args]。"""
        return [self.command, *self.args]

#将请求转换为字典
    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["args"] = list(self.args)
        if self.env is not None:
            data["env"] = dict(self.env)
        return data
