"""Markdown → 终端渲染（Rich）；不可用时退回原文。"""

from __future__ import annotations

from collections.abc import Callable

from backend.app.cli.theme import (
    BORDER_ANSWER,
    get_theme,
    make_console,
    styled_panel,
    terminal_width,
)


def looks_like_markdown(text: str) -> bool:
    if not text:
        return False
    markers = ("```", "# ", "## ", "- ", "* ", "1. ", "`", "**")
    return any(m in text for m in markers)


def render_markdown(
    text: str,
    *,
    output_fn: Callable[[str], None] | None = None,
    force_plain: bool = False,
) -> None:
    """将 Markdown 打印到终端（CodeWisp Panel）。"""
    body = text or ""
    capture = output_fn is not None and output_fn is not print
    plain = force_plain or not get_theme().rich_enabled or capture

    if capture:
        console = make_console(force_plain=True)
        if looks_like_markdown(body):
            from rich.markdown import Markdown

            with console.capture() as cap:
                console.print(Markdown(body, code_theme="monokai"), soft_wrap=True)
            rendered = cap.get().rstrip("\n")
        else:
            rendered = body
        for line in rendered.splitlines() or [""]:
            output_fn(line)  # type: ignore[misc]
        return

    if plain:
        print(body)
        return

    from rich.markdown import Markdown
    from rich.text import Text

    width = terminal_width()
    console = make_console(width=width)
    if looks_like_markdown(body):
        content: object = Markdown(body, code_theme="monokai", justify="left")
    else:
        content = Text(body, overflow="fold", no_wrap=False)

    console.print(
        styled_panel(
            content,
            title="[cw.answer]✦ Final Answer[/]",
            border=BORDER_ANSWER,
            padding=(1, 2),
            width=width,
            subtitle="[dim #94a3b8]CodeWisp[/]",
        ),
        soft_wrap=True,
        overflow="fold",
        crop=False,
        width=width,
    )


def render_markdown_to_string(text: str, *, force_plain: bool = True) -> str:
    console = make_console(force_plain=force_plain)
    body = text or ""
    if looks_like_markdown(body):
        from rich.markdown import Markdown

        with console.capture() as cap:
            console.print(Markdown(body, code_theme="monokai"), soft_wrap=True)
        return cap.get().rstrip("\n")
    return body
