"""CLI 面板：Git / LSP / 小节信息的统一 Rich 展示。"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from backend.app.cli.theme import get_theme, make_console


def _use_rich(output_fn: Callable[[str], None]) -> bool:
    return output_fn is print and get_theme().rich_enabled


def render_section(
    title: str,
    rows: list[tuple[str, str]],
    *,
    output_fn: Callable[[str], None],
    footer: str | None = None,
) -> None:
    """键值对区块。"""
    if _use_rich(output_fn):
        from rich.panel import Panel
        from rich.table import Table
        from rich.text import Text

        table = Table(show_header=False, box=None, padding=(0, 1))
        table.add_column("k", style="cw.key", width=12)
        table.add_column("v", style="cw.value")
        for k, v in rows:
            table.add_row(k, v)
        body = table
        if footer:
            from rich.console import Group

            body = Group(table, Text(), Text(footer, style="cw.dim"))
        make_console().print(
            Panel(body, title=f"[cw.brand]{title}[/]", title_align="left", border_style="cyan", padding=(0, 1))
        )
        return

    output_fn(title)
    output_fn("─" * min(40, max(12, len(title) + 4)))
    for k, v in rows:
        output_fn(f"  {k:<12} {v}")
    if footer:
        output_fn(f"  {footer}")


def render_git_status(status: Any, *, output_fn: Callable[[str], None]) -> None:
    from backend.app.git.models import GitStatus

    if not isinstance(status, GitStatus):
        output_fn("（当前 workspace 不是 Git 仓库）")
        return

    rows = [
        ("Root", status.repository_root),
        ("Branch", status.branch or "(detached)"),
        ("Modified", str(status.modified_count)),
        ("Staged", str(status.staged_count)),
        ("Untracked", str(status.untracked_count)),
        ("Clean", "yes" if status.clean else "no"),
    ]
    render_section("Git Repository", rows, output_fn=output_fn)

    if status.clean or not status.all_files:
        return

    if _use_rich(output_fn):
        from rich.panel import Panel
        from rich.text import Text

        body = Text()
        for f in status.all_files[:40]:
            line = f.display
            if line.startswith("??") or "untracked" in f.status:
                body.append(f"  {line}\n", style="cw.warn")
            elif f.staged:
                body.append(f"  {line}\n", style="cw.ok")
            else:
                body.append(f"  {line}\n", style="cw.diff.file")
        if len(status.all_files) > 40:
            body.append(f"  … +{len(status.all_files) - 40} more\n", style="cw.dim")
        make_console().print(
            Panel(body, title="[cw.info]Working Tree[/]", title_align="left", border_style="dim")
        )
    else:
        output_fn("Files:")
        for f in status.all_files[:40]:
            output_fn(f"  {f.display}")


def render_git_log(commits: list, *, output_fn: Callable[[str], None]) -> None:
    if _use_rich(output_fn):
        from rich.panel import Panel
        from rich.table import Table

        table = Table(show_header=True, box=None, padding=(0, 1))
        table.add_column("Commit", style="cw.info", no_wrap=True)
        table.add_column("Message", style="cw.value")
        for c in commits:
            table.add_row(c.short_id, c.message)
        make_console().print(
            Panel(
                table,
                title=f"[cw.brand]Recent commits[/] ({len(commits)})",
                title_align="left",
                border_style="cyan",
            )
        )
        return
    output_fn(f"Recent commits ({len(commits)}):")
    for c in commits:
        output_fn(f"  {c.render_line()}")


def render_lsp_status(status: Any, *, output_fn: Callable[[str], None]) -> None:
    mark = {
        "available": "✓ available",
        "unavailable": "✗ unavailable",
        "unsupported": "○ unsupported",
        "error": "✗ error",
    }.get(getattr(status.status, "value", str(status.status)), str(status.status))
    rows = [
        ("Workspace", status.workspace),
        ("Language", status.language or "-"),
        ("Server", status.server or "-"),
        ("Status", mark),
    ]
    if status.message:
        rows.append(("Note", status.message))
    render_section("Code Intelligence", rows, output_fn=output_fn)


def render_lsp_diagnostics(
    diags: list,
    *,
    path: str | None,
    output_fn: Callable[[str], None],
) -> None:
    if not diags:
        if _use_rich(output_fn):
            make_console().print("[cw.ok]✓ LSP diagnostics clean[/]")
        else:
            output_fn("✓ clean")
        return

    by_path: dict[str, list] = {}
    for d in diags:
        by_path.setdefault(d.path or path or "?", []).append(d)

    if _use_rich(output_fn):
        from rich.panel import Panel
        from rich.text import Text

        body = Text()
        for p, items in by_path.items():
            body.append(f"{p}\n", style="cw.diff.file")
            for d in items:
                style = {
                    "error": "cw.fail",
                    "warning": "cw.warn",
                    "information": "cw.info",
                    "hint": "cw.dim",
                }.get(d.severity.value, "cw.dim")
                body.append(f"  {d.render_line()}\n", style=style)
            body.append("\n")
        body.append(f"{len(diags)} diagnostics", style="cw.dim")
        make_console().print(
            Panel(
                body,
                title="[cw.brand]LSP Diagnostics[/]",
                title_align="left",
                border_style="yellow",
            )
        )
        return

    output_fn("LSP Diagnostics")
    output_fn("────────────────────────────────")
    for p, items in by_path.items():
        output_fn("")
        output_fn(p)
        for d in items:
            output_fn(f"  {d.render_line()}")
    output_fn("")
    output_fn(f"{len(diags)} diagnostics")


def render_git_diff(diff: Any, *, output_fn: Callable[[str], None]) -> None:
    """GitDiff（仓库级）摘要 + patch，+/- 着色。"""
    summary = diff.render_summary() if hasattr(diff, "render_summary") else str(diff)
    patch = getattr(diff, "patch", None) or ""
    if len(patch) > 8000:
        patch = patch[:8000] + "\n... (truncated)"

    if _use_rich(output_fn):
        from rich.panel import Panel
        from rich.text import Text

        body = Text()
        body.append(summary + "\n\n", style="cw.value")
        if patch:
            for line in patch.splitlines(keepends=True):
                if line.startswith("+") and not line.startswith("+++"):
                    body.append(line, style="cw.diff.add")
                elif line.startswith("-") and not line.startswith("---"):
                    body.append(line, style="cw.diff.del")
                elif line.startswith("@@"):
                    body.append(line, style="cw.diff.hunk")
                elif line.startswith("diff ") or line.startswith("index "):
                    body.append(line, style="cw.diff.file")
                else:
                    body.append(line, style="cw.dim")
        else:
            body.append("(no patch)", style="cw.dim")
        make_console().print(
            Panel(
                body,
                title="[cw.brand]Git Diff[/]",
                title_align="left",
                border_style="cyan",
            )
        )
        return

    output_fn(summary)
    if patch:
        output_fn("")
        output_fn(patch)


def render_git_branches(
    branches: list,
    *,
    current: str | None,
    output_fn: Callable[[str], None],
) -> None:
    rows = [("Current", current or "(detached)")]
    render_section("Git Branches", rows, output_fn=output_fn)
    if _use_rich(output_fn):
        from rich.panel import Panel
        from rich.text import Text

        body = Text()
        for b in branches:
            if b.current:
                body.append(f"  * {b.name}\n", style="cw.ok")
            else:
                body.append(f"    {b.name}\n", style="cw.value")
        make_console().print(
            Panel(body, title="[cw.info]Branches[/]", title_align="left", border_style="dim")
        )
    else:
        output_fn("Branches:")
        for b in branches:
            marker = "*" if b.current else " "
            output_fn(f"  {marker} {b.name}")


def render_lsp_symbols(path: str, symbols: list, *, output_fn: Callable[[str], None]) -> None:
    if _use_rich(output_fn):
        from rich.panel import Panel
        from rich.text import Text

        body = Text()
        if not symbols:
            body.append("  (no symbols)\n", style="cw.dim")
        else:
            for sym in symbols:
                for line in sym.render_tree():
                    body.append(line + "\n", style="cw.value")
        make_console().print(
            Panel(
                body,
                title=f"[cw.brand]Symbols[/] {path}",
                title_align="left",
                border_style="cyan",
            )
        )
        return
    output_fn(path)
    if not symbols:
        output_fn("  (no symbols)")
        return
    for sym in symbols:
        for line in sym.render_tree():
            output_fn(line)
