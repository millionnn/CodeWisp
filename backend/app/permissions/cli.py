"""CliPermissionHandler：终端交互式授权（方向键或 y/n）。"""

#在终端中怎么问用户（方向键或 y/n）
from __future__ import annotations

from collections.abc import Callable

from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.errors import (
    InvalidPermissionDecisionError,
    PermissionInterruptedError,
)
from backend.app.permissions.request import PermissionRequest


class CliPermissionHandler:
    """在 stdout 提示并阻塞读取用户决定。"""

    def __init__(
        self,
        *,
        input_fn: Callable[[str], str | None] | None = None,
        output_fn: Callable[[str], None] | None = None,
    ) -> None:
        self._input_fn = input_fn
        self._output_fn = output_fn or print

    def request(self, permission: PermissionRequest) -> PermissionDecision:
        from backend.app.cli.prompt import interactive_available, read_line
        from backend.app.cli.render_permission import render_permission_prompt
        from backend.app.cli.select import select_option

        render_permission_prompt(permission, output_fn=self._output_fn)

        # 测试注入 / 非 TTY：走 y/n 文本
        if self._input_fn is not None or not interactive_available():
            return self._ask_yn()

        picked = select_option(
            "授权决定",
            [
                (PermissionDecision.ALLOW, "[y] Allow once — 允许本次执行"),
                (PermissionDecision.DENY, "[n] Deny — 拒绝本次执行"),
            ],
            default_index=1,  # 默认 DENY，更安全
            output_fn=self._output_fn,
        )
        if picked is None:
            raise PermissionInterruptedError("授权等待被取消；命令未执行。")
        return picked

    def _ask_yn(self) -> PermissionDecision:
        reader = self._input_fn
        if reader is None:
            from backend.app.cli.prompt import read_line

            reader = read_line

        while True:
            try:
                raw = reader("> ")
            except (EOFError, KeyboardInterrupt) as exc:
                self._output_fn("")
                raise PermissionInterruptedError(
                    "授权等待被中断；命令未执行。"
                ) from exc
            if raw is None:
                raise PermissionInterruptedError(
                    "授权等待被中断（EOF）；命令未执行。"
                )
            try:
                return PermissionDecision.parse(raw)
            except InvalidPermissionDecisionError as exc:
                self._output_fn(f"  {exc}")
                self._output_fn("  请输入 y/yes 或 n/no。")
