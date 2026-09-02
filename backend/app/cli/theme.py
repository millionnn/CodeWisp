"""CLI 主题与 Rich 能力开关（NO_COLOR / 非 TTY / mono 降级）。"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from rich.console import Console
from rich.theme import Theme

# ── 品牌色：青绿主调 + 琥珀警告，避免紫系 AI 默认观感 ──────────────
# 边框 / 标题在 TTY 下用 truecolor；mono / NO_COLOR 走纯文本路径。

CODEWISP_THEME = Theme(
    {
        "cw.brand": "bold #2dd4bf",
        "cw.dim": "dim #94a3b8",
        "cw.ok": "bold #34d399",
        "cw.fail": "bold #f87171",
        "cw.warn": "bold #fbbf24",
        "cw.info": "#38bdf8",
        "cw.user": "bold #60a5fa",
        "cw.agent": "bold #2dd4bf",
        "cw.key": "dim #64748b",
        "cw.value": "#e2e8f0",
        "cw.cmd": "bold #f1f5f9",
        "cw.step": "dim #64748b",
        "cw.plan": "bold #2dd4bf",
        "cw.tool": "dim #67e8f9",
        "cw.answer": "bold #ddd6fe",
        "cw.git": "bold #fb923c",
        "cw.lsp": "bold #38bdf8",
        "cw.border": "#334155",
        "cw.border.accent": "#2dd4bf",
        "cw.border.answer": "#c4b5fd",
        "cw.border.git": "#fb923c",
        "cw.border.lsp": "#38bdf8",
        "cw.border.warn": "#fbbf24",
        "cw.border.ok": "#34d399",
        "cw.diff.file": "bold #e2e8f0",
        "cw.diff.add": "#34d399",
        "cw.diff.del": "#f87171",
        "cw.diff.hunk": "#38bdf8",
        "cw.diff.meta": "dim #64748b",
        "cw.diff.stat": "bold #e2e8f0",
        "cw.rule": "dim #475569",
    }
)

# Panel 边框语义色（传给 border_style）
BORDER_ACCENT = "cw.border.accent"
BORDER_ANSWER = "cw.border.answer"
BORDER_GIT = "cw.border.git"
BORDER_LSP = "cw.border.lsp"
BORDER_MUTED = "cw.border"
BORDER_WARN = "cw.border.warn"
BORDER_OK = "cw.border.ok"


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


def panel_box():
    """统一圆角边框（Rich box）。"""
    from rich import box

    return box.ROUNDED


def styled_panel(
    renderable: Any,
    *,
    title: str | None = None,
    subtitle: str | None = None,
    border: str = BORDER_ACCENT,
    padding: tuple[int, int] = (0, 1),
    expand: bool = True,
    width: int | None = None,
) -> Any:
    """带统一圆角 / 左对齐标题的 Panel。"""
    from rich.panel import Panel

    kwargs: dict[str, Any] = {
        "border_style": border,
        "padding": padding,
        "expand": expand,
        "box": panel_box(),
    }
    if title is not None:
        kwargs["title"] = title
        kwargs["title_align"] = "left"
    if subtitle is not None:
        kwargs["subtitle"] = subtitle
        kwargs["subtitle_align"] = "right"
    if width is not None:
        kwargs["width"] = width
    return Panel(renderable, **kwargs)
