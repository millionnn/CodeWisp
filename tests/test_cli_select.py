"""CLI 输入与方向键选择（非 TTY 编号回退）。"""

from __future__ import annotations

from unittest.mock import patch

from backend.app.cli.select import select_option


def test_select_option_numbered_pick() -> None:
    answers = iter(["2"])
    lines: list[str] = []
    picked = select_option(
        "选一个",
        [("a", "Alpha"), ("b", "Beta"), ("c", "Charlie")],
        default_index=0,
        input_fn=lambda _p: next(answers),
        output_fn=lines.append,
    )
    assert picked == "b"
    assert any("选一个" in line for line in lines)


def test_select_option_default_on_empty() -> None:
    answers = iter([""])
    picked = select_option(
        "选一个",
        [("a", "Alpha"), ("b", "Beta")],
        default_index=1,
        input_fn=lambda _p: next(answers),
        output_fn=lambda _s: None,
    )
    assert picked == "b"


def test_select_option_cancel() -> None:
    answers = iter(["q"])
    picked = select_option(
        "选一个",
        [("a", "Alpha")],
        input_fn=lambda _p: next(answers),
        output_fn=lambda _s: None,
    )
    assert picked is None


def test_select_option_uses_arrows_when_tty_and_no_input_fn() -> None:
    """真实 TTY 且未注入 input_fn 时应走方向键菜单，而非编号输入。"""
    with (
        patch("backend.app.cli.select.interactive_available", return_value=True),
        patch(
            "backend.app.cli.select._select_arrows",
            return_value="arrow-picked",
        ) as arrows,
        patch(
            "backend.app.cli.select._select_numbered",
            return_value="numbered",
        ) as numbered,
    ):
        picked = select_option(
            "选一个",
            [("a", "Alpha"), ("b", "Beta")],
            default_index=0,
        )
    assert picked == "arrow-picked"
    arrows.assert_called_once()
    numbered.assert_not_called()


def test_select_option_injected_input_forces_numbered_even_on_tty() -> None:
    with (
        patch("backend.app.cli.select.interactive_available", return_value=True),
        patch(
            "backend.app.cli.select._select_arrows",
            return_value="arrow-picked",
        ) as arrows,
    ):
        picked = select_option(
            "选一个",
            [("a", "Alpha"), ("b", "Beta")],
            input_fn=lambda _p: "1",
            output_fn=lambda _s: None,
        )
    assert picked == "a"
    arrows.assert_not_called()
