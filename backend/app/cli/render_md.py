"""Markdown → 终端渲染（Rich）；不可用时退回原文。"""

from __future__ import annotations

from collections.abc import Callable

from backend.app.cli.theme import get_theme, make_console

#把回答渲染成好看的md
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
    """将 Markdown 打印到终端。"""
    body = text or ""
    capture = output_fn is not None and output_fn is not print
    plain = force_plain or not get_theme().rich_enabled or capture

    if capture:
        console = make_console(force_plain=True)
        if looks_like_markdown(body):
            from rich.markdown import Markdown

            with console.capture() as cap:
                console.print(Markdown(body, code_theme="monokai"))
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
    from rich.panel import Panel

    console = make_console()
    content: object = Markdown(body, code_theme="monokai") if looks_like_markdown(body) else body
    console.print(
        Panel(
            content,
            title="[cw.agent]CodeWisp[/]",
            border_style="cyan",
            padding=(0, 1),
        )
    )


def render_markdown_to_string(text: str, *, force_plain: bool = True) -> str:
    console = make_console(force_plain=force_plain)
    body = text or ""
    if looks_like_markdown(body):
        from rich.markdown import Markdown

        with console.capture() as cap:
            console.print(Markdown(body, code_theme="monokai"))
        return cap.get().rstrip("\n")
    return body
