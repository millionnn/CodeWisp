"""OpenCode 风格 CLI Footer：左 workspace，右 session / model / tokens。

参考 OpenCode TUI footer（space-between）：
  ~/project                          title · model · 19.1k/58.9k 32%

固定在输入区下方（prompt_toolkit bottom_toolbar），不占用对话区。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from backend.app.cli.theme import get_theme, make_console, terminal_width
from backend.app.session.models import Session


@dataclass
class StatusSnapshot:
    workspace: str = ""
    session_id: str = ""
    title: str = ""
    model: str = ""
    context_used: int | None = None
    context_budget: int | None = None

    def left(self) -> str:
        return _short_path(self.workspace) or "—"

    def right(self) -> str:
        parts: list[str] = []
        title = (self.title or "").strip() or "—"
        if len(title) > 20:
            title = title[:19] + "…"
        parts.append(title)
        model = self.model or "—"
        # OpenCode 风格：优先短 model id
        if "/" in model:
            model = model.split("/", 1)[-1]
        if len(model) > 22:
            model = model[:21] + "…"
        parts.append(model)
        parts.append(self.context_label())
        return " · ".join(parts)

    def context_label(self) -> str:
        if self.context_used is None or self.context_budget is None or self.context_budget <= 0:
            return "ctx —"
        used = _fmt_k(self.context_used)
        budget = _fmt_k(self.context_budget)
        pct = int(round(100.0 * self.context_used / self.context_budget))
        return f"{used}/{budget} {pct}%"

    def line(self, *, width: int | None = None) -> str:
        """单行 footer：左 path，右状态，中间空格填充（优先保证右侧完整）。"""
        right = self.right()
        w = width or terminal_width(fallback=get_theme().width)
        max_left = max(8, w - len(right) - 2)
        left = self.left()
        if len(left) > max_left:
            left = _short_path(self.workspace, max_len=max_left) or left[:max_left]
            if len(left) > max_left:
                left = "…" + left[-(max_left - 1) :]
        gap = w - len(left) - len(right)
        if gap < 1:
            gap = 1
            # 极端窄屏：截右侧
            right = right[: max(0, w - len(left) - 1)]
        return f"{left}{' ' * gap}{right}"


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

    def toolbar_text(self) -> str:
        """prompt_toolkit bottom_toolbar 用纯文本（含填充空格）。"""
        return self.snapshot.line()

    def print_line(self, output_fn: Callable[[str], None] = print) -> None:
        line = self.snapshot.line()
        if output_fn is print and get_theme().rich_enabled:
            left = self.snapshot.left()
            right = self.snapshot.right()
            w = terminal_width(fallback=get_theme().width)
            gap = max(1, w - len(left) - len(right))
            console = make_console(width=w)
            console.print(
                f"[cw.dim]{left}[/]{' ' * gap}[cw.dim]{right}[/]",
                highlight=False,
            )
            return
        output_fn(line)


def _short_path(path: str, *, max_len: int = 28) -> str:
    """OpenCode 风格：优先 ~/…/basename 或 basename。"""
    if not path:
        return ""
    try:
        p = Path(path).expanduser().resolve()
        home = Path.home().resolve()
        try:
            rel = p.relative_to(home)
            text = f"~/{rel.as_posix()}"
        except ValueError:
            text = str(p)
    except OSError:
        text = path
    if len(text) <= max_len:
        return text
    name = Path(text).name
    if len(name) + 2 <= max_len:
        return f"…/{name}"
    if len(name) >= max_len:
        return "…" + name[-(max_len - 1) :]
    return "…" + text[-(max_len - 1) :]


def _fmt_k(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


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
