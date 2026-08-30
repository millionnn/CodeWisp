"""CLI 美化与命令行流式相关测试。"""

from __future__ import annotations

import sys
from pathlib import Path

from backend.app.cli.render_md import looks_like_markdown, render_markdown_to_string
from backend.app.cli.theme import get_theme, reset_theme_cache
from backend.app.execution.request import ExecutionRequest
from backend.app.execution.service import ExecutionService
from backend.app.workspace.workspace import Workspace


def test_looks_like_markdown() -> None:
    assert looks_like_markdown("## Hello\n\n- a")
    assert looks_like_markdown("use `code` here")
    assert not looks_like_markdown("plain text only")


def test_render_markdown_to_string_plain() -> None:
    text = render_markdown_to_string("## Title\n\nHello **world**", force_plain=True)
    assert "Title" in text
    assert "Hello" in text


def test_theme_respects_no_color(monkeypatch) -> None:
    reset_theme_cache()
    monkeypatch.setenv("NO_COLOR", "1")
    reset_theme_cache()
    theme = get_theme()
    assert theme.rich_enabled is False
    reset_theme_cache()
    monkeypatch.delenv("NO_COLOR", raising=False)
    monkeypatch.setenv("CODEWISP_THEME", "mono")
    reset_theme_cache()
    assert get_theme().name == "mono"
    assert get_theme().rich_enabled is False
    reset_theme_cache()


def test_execution_service_on_line_callback(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    service = ExecutionService(ws)
    lines: list[tuple[str, str]] = []

    def on_line(stream: str, line: str) -> None:
        lines.append((stream, line))

    result = service.run(
        ExecutionRequest(
            command=sys.executable,
            args=["-c", "import sys; print('hello'); print('err', file=sys.stderr)"],
            timeout=10,
        ),
        on_line=on_line,
    )
    assert result.success is True
    assert any(s == "stdout" and "hello" in ln for s, ln in lines)
    assert any(s == "stderr" and "err" in ln for s, ln in lines)
