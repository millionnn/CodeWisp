"""LSPContextProvider — code intelligence metadata for ContextManager."""

from __future__ import annotations

from backend.app.lsp.errors import LspError
from backend.app.lsp.manager import LanguageServerManager, get_default_manager
from backend.app.lsp.models import Diagnostic, LspServerStatus, Symbol
from backend.app.lsp.service import LSPService
from backend.app.workspace.workspace import Workspace


class LSPContextProvider:
    """Build LSP metadata summary (no full diagnostic dumps / no full ASTs)."""

    def __init__(
        self,
        workspace: Workspace | str,
        *,
        manager: LanguageServerManager | None = None,
        focus_path: str | None = None,
    ) -> None:
        if isinstance(workspace, str):
            self._workspace = Workspace(workspace)
        else:
            self._workspace = workspace
        self._manager = manager or get_default_manager()
        self._service = LSPService(self._workspace, manager=self._manager)
        self._focus_path = focus_path
        self._cached_text: str | None = None

    def set_focus_path(self, path: str | None) -> None:
        self._focus_path = path

    def refresh(self) -> str:
        self._cached_text = self.build_workspace_context()
        return self._cached_text

    @property
    def cached(self) -> str | None:
        return self._cached_text

    def build_workspace_context(self) -> str:
        status = self._service.status()
        lines = ["## LSP / Code Intelligence"]
        lines.append(f"Language: {status.language or '-'}")
        lines.append(f"Server: {status.server or '-'}")
        lines.append(f"Status: {status.status.value}")

        if status.status is LspServerStatus.UNSUPPORTED:
            lines.append("(no supported language detected)")
            return "\n".join(lines)
        if status.status is not LspServerStatus.AVAILABLE:
            lines.append(f"(unavailable: {status.message or 'no server'})")
            return "\n".join(lines)

        diags: list[Diagnostic] = []
        try:
            diags = self._service.diagnostics(self._focus_path)
        except LspError:
            lines.append("(diagnostics unavailable)")
            return "\n".join(lines)
        except Exception:  # noqa: BLE001
            lines.append("(diagnostics unavailable)")
            return "\n".join(lines)

        errors = sum(1 for d in diags if d.severity.value == "error")
        warnings = sum(1 for d in diags if d.severity.value == "warning")
        lines.append("")
        lines.append(f"Diagnostics: {len(diags)} (errors={errors}, warnings={warnings})")
        for d in diags[:8]:
            path = d.path or self._focus_path or "?"
            loc = d.range.start.display_1based() if d.range else "?"
            lines.append(f"  [{d.severity.value}] {path}:{loc} — {d.message[:120]}")
        if len(diags) > 8:
            lines.append(f"  ... and {len(diags) - 8} more")

        if self._focus_path:
            try:
                symbols = self._service.symbols(self._focus_path)
                flat = _flatten_symbols(symbols)
                lines.append("")
                lines.append(f"Active file symbols ({self._focus_path}): {len(flat)}")
                for sym in flat[:12]:
                    lines.append(f"  - {sym.kind.value}: {sym.name}")
                if len(flat) > 12:
                    lines.append(f"  ... and {len(flat) - 12} more")
            except Exception:  # noqa: BLE001
                pass

        lines.append("")
        lines.append(
            "Tip: use lsp_definition / lsp_references / lsp_symbols / lsp_hover "
            "for on-demand details."
        )
        return "\n".join(lines)


def _flatten_symbols(symbols: list[Symbol], acc: list[Symbol] | None = None) -> list[Symbol]:
    out = acc if acc is not None else []
    for s in symbols:
        out.append(s)
        if s.children:
            _flatten_symbols(s.children, out)
    return out
