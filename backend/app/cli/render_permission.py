"""Permission UI（Rich Panel；降级为纯文本）。"""

from __future__ import annotations

from collections.abc import Callable

from backend.app.cli.theme import BORDER_WARN, get_theme, make_console, styled_panel
from backend.app.permissions.request import PermissionRequest

#权限请求怎么打印

def render_permission_prompt(
    permission: PermissionRequest,
    *,
    output_fn: Callable[[str], None] | None = None,
) -> None:
    argv = " ".join([permission.command, *permission.args]).strip()
    reason = permission.reason or "This operation requires user approval."
    cwd = permission.cwd

    use_rich = get_theme().rich_enabled and (
        output_fn is None or output_fn is print
    )

    if use_rich:
        from rich.text import Text

        body = Text()
        body.append("  ⌘  Command\n", style="cw.key")
        body.append(f"     $ {argv}\n\n", style="cw.cmd")
        body.append("  📂  Working directory\n", style="cw.key")
        body.append(f"     {cwd}\n\n", style="cw.value")
        body.append("  💬  Reason\n", style="cw.key")
        body.append(f"     {reason}\n\n", style="cw.dim")
        body.append("  [y] Allow once", style="cw.ok")
        body.append("    ", style="cw.dim")
        body.append("[n] Deny", style="cw.fail")

        console = make_console()
        console.print()
        console.print(
            styled_panel(
                body,
                title="[cw.warn]⚠ Permission required[/]",
                border=BORDER_WARN,
                padding=(1, 2),
            )
        )
        console.print()
        return

    out = output_fn or print
    out("")
    out("⚠ Permission required")
    out("")
    out("  Command:")
    out(f"    {argv}")
    out("")
    out("  Working directory:")
    out(f"    {cwd}")
    out("")
    out("  Reason:")
    out(f"    {reason}")
    out("")
    out("  [y] Allow once")
    out("  [n] Deny")
    out("")
