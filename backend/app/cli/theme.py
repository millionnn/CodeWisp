"""CLI 主题与 Rich 能力开关（NO_COLOR / 非 TTY / mono 降级）。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache

from rich.console import Console
from rich.theme import Theme

#cli主题

CODEWISP_THEME = Theme(
    {
        "cw.brand": "bold cyan",
        "cw.dim": "dim",
        "cw.ok": "bold green",
        "cw.fail": "bold red",
        "cw.warn": "bold yellow",
        "cw.info": "cyan",
        "cw.user": "bold blue",
        "cw.agent": "bold cyan",
        "cw.key": "dim",
        "cw.value": "white",
        "cw.cmd": "bold white",
        "cw.step": "dim",
        "cw.diff.file": "bold white",
        "cw.diff.add": "green",
        "cw.diff.del": "red",
        "cw.diff.hunk": "cyan",
        "cw.diff.meta": "dim",
        "cw.diff.stat": "bold",
    }
)


@dataclass(frozen=True)
class CliTheme:
    """当前进程的 CLI 展示能力。"""

    rich_enabled: bool
    color: bool
    width: int
    name: str  # default | mono


def terminal_width(*, fallback: int = 100) -> int:
    """读取当前终端列数（不缓存），回答框随窗口缩放。"""
    try:
        cols = os.get_terminal_size(sys.stdout.fileno()).columns
    except (OSError, AttributeError, ValueError):
        try:
            cols = os.get_terminal_size().columns
        except OSError:
            return fallback
    # 不设人为上限，避免宽屏时 Panel 变窄导致观感截断；下限保证可读
    return max(40, cols)


@lru_cache(maxsize=1)
def get_theme() -> CliTheme:
    env_theme = (os.getenv("CODEWISP_THEME") or "default").strip().lower()
    if env_theme not in {"default", "mono"}:
        env_theme = "default"

    no_color = bool(os.getenv("NO_COLOR"))
    force_color = (os.getenv("FORCE_COLOR") or "").strip() not in {"", "0"}
    is_tty = sys.stdout.isatty()

    color = False if no_color or env_theme == "mono" else (force_color or is_tty)
    rich_enabled = color  # mono/NO_COLOR → 纯文本路径，便于测试与管道

    return CliTheme(
        rich_enabled=rich_enabled,
        color=color,
        width=terminal_width(),
        name=env_theme,
    )


def reset_theme_cache() -> None:
    """测试用：清缓存。"""
    get_theme.cache_clear()


def make_console(*, force_plain: bool = False, width: int | None = None) -> Console:
    theme = get_theme()
    plain = force_plain or not theme.rich_enabled
    # 每次渲染用最新终端宽度，窗口缩放后回答框立即适配
    w = width if width is not None else terminal_width(fallback=theme.width)
    return Console(
        theme=CODEWISP_THEME,
        width=w,
        highlight=False,
        soft_wrap=True,
        force_terminal=False if plain else None,
        no_color=plain,
        color_system=None if plain else "auto",
    )


def style(text: str, style_name: str, *, force_plain: bool = False) -> str:
    """返回带样式的字符串；plain 时原样返回。"""
    if force_plain or not get_theme().rich_enabled:
        return text
    console = make_console(force_plain=False)
    with console.capture() as cap:
        console.print(text, style=style_name, end="")
    return cap.get()
