"""OpenCode 风格 CLI Footer：左 workspace，右 session / model / tokens。

参考 OpenCode TUI footer（space-between）：
  ~/project                          title · model · ctx 19100/58900

固定在输入区下方（prompt_toolkit bottom_toolbar），不占用对话区。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.cli.theme import get_theme, make_console, terminal_width
from backend.app.session.models import Session

# prompt_toolkit bottom_toolbar 内联色（透明底，仅前景分色）
_BASE = "noreverse"
_STY_PATH = f"fg:#2dd4bf bold {_BASE}"
_STY_TITLE = f"fg:#94a3b8 {_BASE}"
_STY_SEP = f"fg:#64748b {_BASE}"
_STY_MODEL = f"fg:#67e8f9 {_BASE}"
_STY_CTX = f"fg:#fbbf24 {_BASE}"
_STY_GAP = _BASE


@dataclass
class StatusSnapshot:
    workspace: str = ""
    session_id: str = ""
    title: str = ""
    model: str = ""
    context_used: int | None = None
    context_budget: int | None = None

    def left(self) -> str:
        return _home_path(self.workspace) or "—"

    def title_part(self) -> str:
        title = (self.title or "").strip() or "—"
        if len(title) > 20:
            title = title[:19] + "…"
        return title

    def model_part(self) -> str:
        model = self.model or "—"
        if "/" in model:
            model = model.split("/", 1)[-1]
        if len(model) > 22:
            model = model[:21] + "…"
        return model

    def right(self) -> str:
        return " · ".join(
            [self.title_part(), self.model_part(), self.context_label()]
        )

    def context_label(self) -> str:
        """完整整数 token，不缩写成 k。"""
        used = self.context_used
        budget = self.context_budget
        if used is None and (budget is None or budget <= 0):
            return "ctx 0"
        if used is None:
            used = 0
        if budget is None or budget <= 0:
            return f"ctx {used:,}"
        return f"ctx {used:,}/{budget:,}"

    def line(self, *, width: int | None = None) -> str:
        """单行 footer：左 path，右状态，中间空格填充（优先保证右侧完整）。"""
        right = self.right()
        w = width or terminal_width(fallback=get_theme().width)
        max_left = max(8, w - len(right) - 2)
        left = _fit_path(self.workspace, max_left)
        gap = w - len(left) - len(right)
        if gap < 1:
            gap = 1
            right = right[: max(0, w - len(left) - 1)]
        return f"{left}{' ' * gap}{right}"

    def formatted(self, *, width: int | None = None) -> Any:
        """prompt_toolkit FormattedText：分色左 path / 右 title·model·ctx。"""
        from prompt_toolkit.formatted_text import FormattedText

        title = self.title_part()
        model = self.model_part()
        ctx = self.context_label()
        right_plain = f"{title} · {model} · {ctx}"
        w = width or terminal_width(fallback=get_theme().width)
        max_left = max(8, w - len(right_plain) - 2)
        left = _fit_path(self.workspace, max_left)
        gap = max(1, w - len(left) - len(right_plain))
        return FormattedText(
            [
                (_STY_PATH, f" {left}"),
                (_STY_GAP, " " * max(0, gap - 1)),
                (_STY_TITLE, title),
                (_STY_SEP, " · "),
                (_STY_MODEL, model),
                (_STY_SEP, " · "),
                (_STY_CTX, ctx),
                (_STY_GAP, " "),
            ]
        )


@dataclass
class StatusBarState:
    """跨 prompt 复用的状态；由 CLI 主循环更新。"""

    snapshot: StatusSnapshot = field(default_factory=StatusSnapshot)
    show_todos: bool = True  # 与 Claude Code Ctrl+T 对应；默认展开

    def update_workspace(self, workspace: Path | str | None) -> None:
        if workspace is None:
            self.snapshot.workspace = ""
        else:
            self.snapshot.workspace = str(workspace)

    def update_from_session(self, session: Session) -> None:
        self.snapshot.session_id = session.session_id
        self.snapshot.title = session.title
        self.snapshot.model = f"{session.provider_id}/{session.model_id}"
        if session.workspace:
            self.snapshot.workspace = str(session.workspace)

    def update_context(self, *, used: int | None, budget: int | None) -> None:
        self.snapshot.context_used = used
        self.snapshot.context_budget = budget

    def toolbar_text(self) -> Any:
        """prompt_toolkit bottom_toolbar：彩色 FormattedText。"""
        return self.snapshot.formatted()

    def print_line(self, output_fn: Callable[[str], None] = print) -> None:
        line = self.snapshot.line()
        if output_fn is print and get_theme().rich_enabled:
            w = terminal_width(fallback=get_theme().width)
            title = self.snapshot.title_part()
            model = self.snapshot.model_part()
            ctx = self.snapshot.context_label()
            right_len = len(f"{title} · {model} · {ctx}")
            left = _fit_path(self.snapshot.workspace, max(8, w - right_len - 2))
            gap = max(1, w - len(left) - right_len)
            console = make_console(width=w)
            console.print(
                f"[cw.brand]{left}[/]{' ' * gap}"
                f"[cw.value]{title}[/][cw.dim] · [/]"
                f"[cw.info]{model}[/][cw.dim] · [/]"
                f"[cw.warn]{ctx}[/]",
                highlight=False,
            )
            return
        output_fn(line)


def _home_path(path: str) -> str:
    """把绝对路径收成 ~/… 形式（不截断）。"""
    if not path:
        return ""
    try:
        p = Path(path).expanduser().resolve()
        home = Path.home().resolve()
        try:
            return f"~/{p.relative_to(home).as_posix()}"
        except ValueError:
            return str(p)
    except OSError:
        return path


def _fit_path(path: str, max_len: int) -> str:
    """按可用宽度截断路径；优先保留 ~/ 与末段目录名。"""
    text = _home_path(path) or "—"
    if len(text) <= max_len:
        return text
    name = Path(text).name
    if len(name) + 2 <= max_len:
        return f"…/{name}"
    if len(name) >= max_len:
        return "…" + name[-(max_len - 1) :]
    return "…" + text[-(max_len - 1) :]


def summarize_session_title(message: str, *, max_len: int = 48) -> str:
    """用首条用户消息生成 Session 标题。"""
    text = " ".join((message or "").strip().split())
    if not text:
        return "Untitled"
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "…"


DEFAULT_SESSION_TITLES = frozenset(
    {
        "CLI Session",
        "cli session",
        "Untitled",
    }
)
