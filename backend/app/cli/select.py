"""方向键选择菜单（↑↓ 移动，Enter 确认，Esc/q 取消）。

交互 TTY：选完后擦除菜单，只留下一行确认结果（避免选项永久刷屏）。
"""

from __future__ import annotations

import sys
from typing import TypeVar

from backend.app.cli.prompt import interactive_available

T = TypeVar("T")


def select_option(
    title: str,
    choices: list[tuple[T, str]],
    *,
    default_index: int = 0,
    input_fn=None,
    output_fn=None,
    collapse: bool = True,
) -> T | None:
    """从选项中选一项。

    choices: ``(value, label)`` 列表。
    交互 TTY：↑↓ + Enter；否则编号输入（便于测试）。
    取消返回 None。
    collapse：箭头模式下选完擦菜单，只留确认行。
    """
    if not choices:
        return None

    out = output_fn or print
    if input_fn is not None or not interactive_available():
        return _select_numbered(
            title,
            choices,
            default_index=default_index,
            input_fn=input_fn,
            output_fn=out,
        )

    try:
        return _select_arrows(
            title, choices, default_index=default_index, collapse=collapse
        )
    except Exception:  # noqa: BLE001
        return _select_numbered(
            title, choices, default_index=default_index, input_fn=None, output_fn=out
        )


def _menu_line_count(choices: list) -> int:
    # title + hint + blank + N choices（与 _render 一致）
    return 3 + len(choices)


def _erase_lines(n: int) -> None:
    if n <= 0 or not sys.stdout.isatty():
        return
    out = sys.stdout
    out.write(f"\033[{n}A")
    for _ in range(n):
        out.write("\033[2K\n")
    out.write(f"\033[{n}A")
    out.flush()


def _print_selection(label: str, *, cancelled: bool = False) -> None:
    try:
        from backend.app.cli.theme import get_theme, make_console

        if sys.stdout.isatty() and get_theme().rich_enabled:
            console = make_console()
            if cancelled:
                console.print("[cw.dim]  (已取消)[/]")
            else:
                console.print(f"[cw.ok]  ✓[/] [cw.value]{label}[/]")
            return
    except Exception:  # noqa: BLE001
        pass
    if cancelled:
        print("  (已取消)")
    else:
        print(f"  ✓ {label}")


def _select_arrows(
    title: str,
    choices: list[tuple[T, str]],
    *,
    default_index: int,
    collapse: bool = True,
) -> T | None:
    from prompt_toolkit.application import Application
    from prompt_toolkit.key_binding import KeyBindings
    from prompt_toolkit.layout import Layout
    from prompt_toolkit.layout.containers import HSplit, Window
    from prompt_toolkit.layout.controls import FormattedTextControl
    from prompt_toolkit.styles import Style

    index = {"i": max(0, min(default_index, len(choices) - 1))}
    result: dict[str, T | None] = {"value": None, "cancel": False}
    lines_drawn = _menu_line_count(choices)

    def _render() -> list[tuple[str, str]]:
        lines: list[tuple[str, str]] = [
            ("class:title", f"◆ {title}\n"),
            ("class:hint", "↑↓ 选择 · Enter 确认 · Esc 取消\n\n"),
        ]
        for i, (_val, label) in enumerate(choices):
            if i == index["i"]:
                lines.append(("class:selected", f" ❯ {label}\n"))
            else:
                lines.append(("class:item", f"   {label}\n"))
        return lines

    kb = KeyBindings()

    @kb.add("up")
    @kb.add("c-p")
    def _up(event) -> None:  # type: ignore[no-untyped-def]
        index["i"] = (index["i"] - 1) % len(choices)
        event.app.invalidate()

    @kb.add("down")
    @kb.add("c-n")
    def _down(event) -> None:  # type: ignore[no-untyped-def]
        index["i"] = (index["i"] + 1) % len(choices)
        event.app.invalidate()

    @kb.add("left")
    def _left(event) -> None:  # type: ignore[no-untyped-def]
        index["i"] = (index["i"] - 1) % len(choices)
        event.app.invalidate()

    @kb.add("right")
    def _right(event) -> None:  # type: ignore[no-untyped-def]
        index["i"] = (index["i"] + 1) % len(choices)
        event.app.invalidate()

    @kb.add("enter")
    def _enter(event) -> None:  # type: ignore[no-untyped-def]
        result["value"] = choices[index["i"]][0]
        event.app.exit()

    @kb.add("escape")
    @kb.add("c-c")
    @kb.add("q")
    def _cancel(event) -> None:  # type: ignore[no-untyped-def]
        result["cancel"] = True
        event.app.exit()

    style = Style.from_dict(
        {
            "title": "bold cyan",
            "hint": "italic #6b7280",
            "selected": "bold reverse cyan",
            "item": "#d1d5db",
        }
    )
    control = FormattedTextControl(_render, focusable=True)
    app: Application[None] = Application(
        layout=Layout(HSplit([Window(control)])),
        key_bindings=kb,
        style=style,
        full_screen=False,
    )
    app.run()

    if collapse:
        _erase_lines(lines_drawn)

    if result["cancel"]:
        if collapse:
            _print_selection("", cancelled=True)
        return None

    label = choices[index["i"]][1]
    if collapse:
        _print_selection(label)
    return result["value"]


def _select_numbered(
    title: str,
    choices: list[tuple[T, str]],
    *,
    default_index: int,
    input_fn,
    output_fn,
) -> T | None:
    output_fn(title)
    output_fn("（输入序号确认；空行=默认；q=取消）")
    for i, (_val, label) in enumerate(choices, start=1):
        mark = ">" if i - 1 == default_index else " "
        output_fn(f"{mark} {i}. {label}")
    reader = input_fn or (lambda p: _safe_input(p))
    raw = reader("> ")
    if raw is None:
        return None
    text = str(raw).strip().lower()
    if text in {"", "q", "quit", "n", "no"}:
        if text == "":
            picked = choices[default_index][0]
            output_fn(f"  ✓ {choices[default_index][1]}")
            return picked
        output_fn("  (已取消)")
        return None
    if text.isdigit():
        idx = int(text) - 1
        if 0 <= idx < len(choices):
            output_fn(f"  ✓ {choices[idx][1]}")
            return choices[idx][0]
    output_fn("无效选择。")
    return None


def _safe_input(prompt: str) -> str | None:
    try:
        return input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return None
