"""Banner 渲染测试。"""

from __future__ import annotations

from backend.app.banner import (
    APP_NAME,
    ASCII_BANNER,
    COPYRIGHT,
    TAGLINE,
    __version__,
    format_banner,
    print_app_banner,
)


def test_format_banner_contains_logo_version_copyright() -> None:
    text = format_banner()
    assert "CodeWisp" in APP_NAME
    assert ASCII_BANNER in text
    assert f"v{__version__}" in text
    assert COPYRIGHT in text
    assert "Coding Agent" in text


def test_print_app_banner_outputs_lines() -> None:
    lines: list[str] = []
    print_app_banner(output_fn=lines.append)
    joined = "\n".join(lines)
    assert APP_NAME in joined
    assert __version__ in joined
    assert TAGLINE.split()[0] in joined or "Coding Agent" in joined
