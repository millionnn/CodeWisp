"""CLI 输入：修复中文/多字节退格，支持历史与基础编辑。"""

from __future__ import annotations

import sys
from collections.abc import Callable
from pathlib import Path

_SESSION = None


def _history_path() -> Path:
    return Path.home() / ".codewisp" / "cli_history"


def _get_session():
    global _SESSION
    if _SESSION is not None:
        return _SESSION
    try:
        from prompt_toolkit import PromptSession
        from prompt_toolkit.history import FileHistory
        from prompt_toolkit.output import create_output

        hist = _history_path()
        hist.parent.mkdir(parents=True, exist_ok=True)
        _SESSION = PromptSession(
            history=FileHistory(str(hist)),
            enable_history_search=True,
            multiline=False,
            wrap_lines=True,
            mouse_support=False,
            # 对宽字符（中文等）正确计算光标与退格
            output=create_output(stdout=sys.stdout),
        )
    except Exception:  # noqa: BLE001 — 降级到 input()
        _SESSION = False
    return _SESSION


def interactive_available() -> bool:
    return bool(sys.stdin.isatty() and sys.stdout.isatty())


def read_line(
    prompt: str = "> ",
    *,
    bottom_toolbar: Callable[[], str | None] | str | None = None,
) -> str | None:
    """读取一行用户输入；支持退格/方向键/历史；可选 OpenCode 风格底部 footer。"""
    if not interactive_available():
        return _fallback_input(prompt)

    session = _get_session()
    if session is False or session is None:
        return _fallback_input(prompt)

    try:
        from prompt_toolkit.patch_stdout import patch_stdout
        from prompt_toolkit.styles import Style as PtStyle

        kwargs: dict = {}
        if bottom_toolbar is not None:
            kwargs["bottom_toolbar"] = bottom_toolbar
            # OpenCode-like muted footer
            kwargs["style"] = PtStyle.from_dict(
                {
                    "bottom-toolbar": "noreverse fg:#808080",
                    "bottom-toolbar.text": "noreverse fg:#808080",
                }
            )

        with patch_stdout():
            text = session.prompt(prompt, **kwargs)
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    return text.strip()

def _fallback_input(prompt: str) -> str | None:
    try:
        # 尽量启用 readline（对拉丁字符退格有帮助；中文仍可能弱）
        try:
            import readline  # noqa: F401
        except ImportError:
            pass
        line = input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    return line.strip()
