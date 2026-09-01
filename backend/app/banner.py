"""CodeWisp CLI / 后端启动 Banner。"""

from __future__ import annotations

from collections.abc import Callable

__version__ = "1.3.0"
APP_NAME = "CodeWisp"
TAGLINE = "From-scratch Coding Agent Runtime"
COPYRIGHT = "Copyright (c) 2026 CodeWisp Authors"
LICENSE_LINE = "Licensed for local development and evaluation."

# 等宽 ASCII 大字（约 56 列）
ASCII_BANNER = r"""
   ______          __    _       ___         
  / ____/___  ____/ /__ | |     / (_)________
 / /   / __ \/ __  / _ \| | /| / / / ___/ __ \
/ /___/ /_/ / /_/ /  __/| |/ |/ / (__  ) /_/ /
\____/\____/\__,_/\___/ |__/|__/_/____/ .___/ 
                                     /_/     
""".strip(
    "\n"
)


def format_banner(
    *,
    version: str | None = None,
    include_meta: bool = True,
) -> str:
    """返回完整 Banner 文本（不含会话/工作区动态信息）。"""
    ver = version or __version__
    lines = [
        ASCII_BANNER,
        "",
        f"  {APP_NAME}  v{ver}",
        f"  {TAGLINE}",
    ]
    if include_meta:
        lines.extend(
            [
                "",
                f"  {COPYRIGHT}",
                f"  {LICENSE_LINE}",
            ]
        )
    return "\n".join(lines)


def print_app_banner(
    *,
    version: str | None = None,
    output_fn: Callable[[str], None] = print,
) -> None:
    """打印 ASCII Banner + 版本/标语（TTY 下带品牌色，无边框）。"""
    if output_fn is print:
        try:
            import sys

            from backend.app.cli.theme import get_theme, make_console

            if sys.stdout.isatty() and get_theme().rich_enabled:
                from rich.text import Text

                ver = version or __version__
                body = Text()
                # 大字：青绿渐变感（顶亮底稍暗）
                art_lines = ASCII_BANNER.split("\n")
                for i, ln in enumerate(art_lines):
                    sty = "bold #5eead4" if i < len(art_lines) // 2 else "bold #2dd4bf"
                    body.append(ln + "\n", style=sty)
                body.append("\n")
                body.append("  ✦ ", style="bold #fbbf24")
                body.append(f"{APP_NAME}", style="bold #f8fafc")
                body.append(f"  v{ver}\n", style="#67e8f9")
                body.append(f"  {TAGLINE}", style="dim #94a3b8")
                console = make_console()
                console.print()
                console.print(body)
                console.print()
                return
        except Exception:  # noqa: BLE001
            pass
    output_fn(format_banner(version=version, include_meta=False))
    output_fn("")
