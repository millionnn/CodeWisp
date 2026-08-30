"""CodeWisp CLI / 后端启动 Banner。"""

from __future__ import annotations

from collections.abc import Callable

# 与当前里程碑对齐（V0.6 Session & Backend）
__version__ = "0.6.0"
APP_NAME = "CodeWisp"
TAGLINE = "From-scratch Coding Agent Runtime"
COPYRIGHT = "Copyright (c) 2026 CodeWisp Authors"
LICENSE_LINE = "Licensed for local development and evaluation."

# 等宽 ASCII 大字（约 56 列，常见终端可完整显示）
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
    """打印 ASCII Banner + 版本/版权。"""
    output_fn(format_banner(version=version))
    output_fn("")
