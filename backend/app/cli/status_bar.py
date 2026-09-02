"""OpenCode 风格 CLI Footer：左 workspace，右 session / model / tokens。

参考 OpenCode TUI footer（space-between）：
  ~/project                          title · model · 19.1k/58.9k 32%

固定在输入区下方（prompt_toolkit bottom_toolbar），不占用对话区。
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from backend.app.cli.theme import get_theme, make_console, terminal_width
from backend.app.session.models import Session

# prompt_toolkit bottom_toolbar 内联色（透明底，分语义着色）
_BASE = "noreverse"
_STY_PATH = f"fg:#2dd4bf bold {_BASE}"
_STY_TITLE = f"fg:#c4b5fd {_BASE}"  # 淡紫 session 标题
_STY_SEP = f"fg:#64748b {_BASE}"
_STY_MODEL = f"fg:#67e8f9 {_BASE}"
_STY_TOK_USED = f"fg:#fbbf24 bold {_BASE}"
_STY_TOK_BUDGET = f"fg:#94a3b8 {_BASE}"
_STY_TOK_PCT_OK = f"fg:#34d399 {_BASE}"
_STY_TOK_PCT_WARN = f"fg:#fb923c {_BASE}"
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
        """模型 context：已用/预算（k）+ 占用百分比。"""
        used, mid, pct = self._context_parts()
        if not mid:
            return used
        return f"{used}{mid}{pct}"

    def _context_parts(self) -> tuple[str, str, str]:
        used_n = self.context_used if self.context_used is not None else 0
        budget = self.context_budget
        used_s = _fmt_k(used_n)
        if budget is None or budget <= 0:
            return used_s, "", ""
        pct_n = min(100, int(round(100.0 * used_n / budget)))
        return used_s, f"/{_fmt_k(budget)}", f" {pct_n}%"

    def _context_pct(self) -> int:
        used = self.context_used if self.context_used is not None else 0
        budget = self.context_budget
        if budget is None or budget <= 0:
            return 0
        return min(100, int(round(100.0 * used / budget)))

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
        used_s, mid_s, pct_s = self._context_parts()
        ctx_plain = f"{used_s}{mid_s}{pct_s}" if mid_s else used_s
        right_plain = f"{title} · {model} · {ctx_plain}"
        w = width or terminal_width(fallback=get_theme().width)
        max_left = max(8, w - len(right_plain) - 2)
        left = _fit_path(self.workspace, max_left)
        gap = max(1, w - len(left) - len(right_plain))
        pct_sty = _STY_TOK_PCT_WARN if self._context_pct() >= 75 else _STY_TOK_PCT_OK
        parts: list[tuple[str, str]] = [
            (_STY_PATH, f" {left}"),
            (_STY_GAP, " " * max(0, gap - 1)),
            (_STY_TITLE, title),
            (_STY_SEP, " · "),
            (_STY_MODEL, model),
            (_STY_SEP, " · "),
            (_STY_TOK_USED, used_s),
        ]
        if mid_s:
            parts.extend(
                [
                    (_STY_TOK_BUDGET, mid_s),
                    (pct_sty, pct_s),
                ]
            )
        parts.append((_STY_GAP, " "))
        return FormattedText(parts)


@dataclass
class StatusBarState:
    """跨 prompt 复用的状态；由 CLI 主循环更新。"""

    snapshot: StatusSnapshot = field(default_factory=StatusSnapshot)
    show_todos: bool = True  # 与 Claude Code Ctrl+T 对应；默认展开
    _toolbar_cache: Any | None = field(default=None, repr=False)
    _toolbar_cache_width: int = field(default=0, repr=False)

    def update_workspace(self, workspace: Path | str | None) -> None:
        if workspace is None:
            self.snapshot.workspace = ""
        else:
            self.snapshot.workspace = str(workspace)
        self._invalidate_toolbar_cache()

    def update_from_session(self, session: Session) -> None:
        self.snapshot.session_id = session.session_id
        self.snapshot.title = session.title
        self.snapshot.model = f"{session.provider_id}/{session.model_id}"
        if session.workspace:
            self.snapshot.workspace = str(session.workspace)
        self._invalidate_toolbar_cache()
    def update_context(self, *, used: int | None, budget: int | None) -> None:
        self.snapshot.context_used = used
        self.snapshot.context_budget = budget
        self._invalidate_toolbar_cache()

    def _invalidate_toolbar_cache(self) -> None:
        self._toolbar_cache = None
        self._toolbar_cache_width = 0

    def toolbar_text(self) -> Any:
        """prompt_toolkit bottom_toolbar：彩色 FormattedText（缓存，避免每键重算）。"""
        w = terminal_width(fallback=get_theme().width)
        if self._toolbar_cache is not None and self._toolbar_cache_width == w:
            return self._toolbar_cache
        self._toolbar_cache = self.snapshot.formatted(width=w)
        self._toolbar_cache_width = w
        return self._toolbar_cache

    def print_line(self, output_fn: Callable[[str], None] = print) -> None:
        line = self.snapshot.line()
        if output_fn is print and get_theme().rich_enabled:
            w = terminal_width(fallback=get_theme().width)
            title = self.snapshot.title_part()
            model = self.snapshot.model_part()
            used_s, mid_s, pct_s = self.snapshot._context_parts()
            ctx_plain = f"{used_s}{mid_s}{pct_s}" if mid_s else used_s
            right_len = len(f"{title} · {model} · {ctx_plain}")
            left = _fit_path(self.snapshot.workspace, max(8, w - right_len - 2))
            gap = max(1, w - len(left) - right_len)
            pct = self.snapshot._context_pct()
            pct_sty = "cw.warn" if pct >= 75 else "cw.ok"
            console = make_console(width=w)
            if mid_s:
                tok = (
                    f"[cw.warn]{used_s}[/][cw.dim]{mid_s}[/]"
                    f"[{pct_sty}]{pct_s}[/]"
                )
            else:
                tok = f"[cw.dim]{used_s}[/]"
            console.print(
                f"[cw.brand]{left}[/]{' ' * gap}"
                f"[cw.answer]{title}[/][cw.dim] · [/]"
                f"[cw.info]{model}[/][cw.dim] · [/]"
                f"{tok}",
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


def _fmt_k(n: int) -> str:
    """Token 数：≥1k 时用一位小数 k。"""
    n = max(0, int(n))
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
