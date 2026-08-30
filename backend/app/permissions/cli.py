"""CliPermissionHandler：终端交互式 y/n 授权。"""

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
        self._input_fn = input_fn or _default_input
        self._output_fn = output_fn or print

    def request(self, permission: PermissionRequest) -> PermissionDecision:
        from backend.app.cli.render_permission import render_permission_prompt

        render_permission_prompt(permission, output_fn=self._output_fn)

        while True:
            try:
                raw = self._input_fn("> ")
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


def _default_input(prompt: str) -> str | None:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        return None
