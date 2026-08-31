"""CLI Diff 展示。"""

from __future__ import annotations

import difflib
import re
from collections.abc import Callable

from backend.app.changes.models import ChangeType, FileDiff
from backend.app.cli.theme import get_theme, make_console

_HUNK_RE = re.compile(r"^@@ -(\d+)(?:,\d+)? \+(\d+)(?:,\d+)? @@")

#在终端里把 diff 画好看：文件块、绿+/红-、行号、统计

def _count_line_stats(diff: FileDiff) -> tuple[int, int]:
    adds = dels = 0
    for _old_ln, _new_ln, kind, _text in _iter_numbered_lines(diff):
        if kind == "+":
            adds += 1
        elif kind == "-":
            dels += 1
    return adds, dels


def _iter_numbered_lines(
    diff: FileDiff,
) -> list[tuple[int | None, int | None, str, str]]:
    """生成 (old_lineno, new_lineno, kind, text)。

    kind: ' ' context | '-' delete | '+' add | '@' hunk | 'meta'
    """
    before_lines = (diff.before or "").splitlines()
    after_lines = (diff.after or "").splitlines()
    # unified_diff 需要带换行才能稳定产出 hunk
    a = [ln + "\n" for ln in before_lines]
    b = [ln + "\n" for ln in after_lines]
    raw = list(
        difflib.unified_diff(
            a,
            b,
            fromfile=f"a/{diff.path}",
            tofile=f"b/{diff.path}",
            lineterm="\n",
        )
    )
    rows: list[tuple[int | None, int | None, str, str]] = []
    old_ln: int | None = None
    new_ln: int | None = None
    for line in raw:
        text = line.rstrip("\n")
        if text.startswith("---") or text.startswith("+++"):
            rows.append((None, None, "meta", text))
            continue
        m = _HUNK_RE.match(text)
        if m:
            old_ln = int(m.group(1))
            new_ln = int(m.group(2))
            rows.append((None, None, "@", text))
            continue
        if text.startswith("-"):
            rows.append((old_ln, None, "-", text[1:]))
            if old_ln is not None:
                old_ln += 1
        elif text.startswith("+"):
            rows.append((None, new_ln, "+", text[1:]))
            if new_ln is not None:
                new_ln += 1
        elif text.startswith(" "):
            rows.append((old_ln, new_ln, " ", text[1:]))
            if old_ln is not None:
                old_ln += 1
            if new_ln is not None:
                new_ln += 1
        else:
            rows.append((None, None, "meta", text))
    return rows


def _format_lineno(n: int | None, width: int) -> str:
    if n is None:
        return " " * width
    return f"{n:>{width}}"


def format_numbered_diff(diff: FileDiff) -> str:
    """纯文本带行号的 unified 风格 diff。"""
    rows = _iter_numbered_lines(diff)
    width = 1
    for old_n, new_n, _k, _t in rows:
        for n in (old_n, new_n):
            if n is not None:
                width = max(width, len(str(n)))
    lines: list[str] = []
    for old_n, new_n, kind, text in rows:
        if kind in {"meta", "@"}:
            lines.append(text)
            continue
        mark = {" ": " ", "-": "-", "+": "+"}.get(kind, " ")
        lines.append(
            f"{_format_lineno(old_n, width)} {_format_lineno(new_n, width)} {mark} {text}"
        )
    return "\n".join(lines)


def render_file_diffs(
    diffs: list[FileDiff],
    *,
    title: str,
    output_fn: Callable[[str], None],
) -> None:
    """渲染一组 FileDiff：汇总 + 每文件 Panel/纯文本（含行号）。"""
    real = [d for d in diffs if d.change_type is not ChangeType.UNCHANGED]
    if not real:
        output_fn("（无文件变更）")
        return

    total_add = total_del = 0
    for d in real:
        a, b = _count_line_stats(d)
        total_add += a
        total_del += b

    use_rich = output_fn is print and get_theme().rich_enabled
    if use_rich:
        console = make_console()
        console.print(
            f"[cw.info]{title}[/]  "
            f"[cw.diff.stat]{len(real)} file(s)[/]  "
            f"[cw.diff.add]+{total_add}[/] "
            f"[cw.diff.del]-{total_del}[/]"
        )
        console.print()
        for item in real:
            _render_one_rich(console, item)
    else:
        output_fn(f"{title}  {len(real)} file(s)  +{total_add} -{total_del}\n")
        for item in real:
            _render_one_plain(item, output_fn)


def _badge(change: ChangeType) -> str:
    return {
        ChangeType.ADDED: "A",
        ChangeType.DELETED: "D",
        ChangeType.MODIFIED: "M",
        ChangeType.UNCHANGED: " ",
    }.get(change, "?")


def _render_one_rich(console, item: FileDiff) -> None:
    from rich.panel import Panel
    from rich.text import Text

    adds, dels = _count_line_stats(item)
    header = Text()
    header.append(f" {_badge(item.change_type)} ", style="bold reverse")
    header.append(f" {item.path} ", style="cw.diff.file")
    header.append(f" +{adds} ", style="cw.diff.add")
    header.append(f"-{dels}", style="cw.diff.del")

    rows = _iter_numbered_lines(item)
    width = 1
    for old_n, new_n, _k, _t in rows:
        for n in (old_n, new_n):
            if n is not None:
                width = max(width, len(str(n)))

    body = Text()
    for old_n, new_n, kind, text in rows:
        if kind == "@":
            body.append(text + "\n", style="cw.diff.hunk")
            continue
        if kind == "meta":
            body.append(text + "\n", style="cw.diff.meta")
            continue
        body.append(f"{_format_lineno(old_n, width)} ", style="cw.diff.meta")
        body.append(f"{_format_lineno(new_n, width)} ", style="cw.diff.meta")
        if kind == "+":
            body.append(f"+ {text}\n", style="cw.diff.add")
        elif kind == "-":
            body.append(f"- {text}\n", style="cw.diff.del")
        else:
            body.append(f"  {text}\n", style="cw.dim")

    console.print(
        Panel(
            body,
            title=header,
            title_align="left",
            border_style="dim",
            padding=(0, 1),
        )
    )
    console.print()


def _render_one_plain(item: FileDiff, output_fn: Callable[[str], None]) -> None:
    adds, dels = _count_line_stats(item)
    output_fn(f"[{_badge(item.change_type)}] {item.path}  +{adds} -{dels}")
    output_fn(format_numbered_diff(item))
    output_fn("")
