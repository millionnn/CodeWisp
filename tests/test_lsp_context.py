"""LSP context provider tests."""

from __future__ import annotations

from pathlib import Path

from backend.app.context.budget import ContextBudget
from backend.app.lsp.adapters import FakeLanguageServerClient
from backend.app.lsp.context import LSPContextProvider
from backend.app.lsp.manager import LanguageServerManager
from backend.app.lsp.models import (
    Diagnostic,
    DiagnosticSeverity,
    Position,
    Range,
    Symbol,
    SymbolKind,
)


def test_lsp_context_metadata(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text("def add(a,b): return a+b\n", encoding="utf-8")
    fake = FakeLanguageServerClient(
        diagnostics=[
            Diagnostic(
                message="oops",
                severity=DiagnosticSeverity.ERROR,
                path="calc.py",
                range=Range(start=Position(0, 0), end=Position(0, 1)),
            )
        ],
        symbols={
            "calc.py": [
                Symbol(
                    name="add",
                    kind=SymbolKind.FUNCTION,
                    range=Range(start=Position(0, 0), end=Position(0, 3)),
                    path="calc.py",
                )
            ]
        },
    )
    manager = LanguageServerManager()
    manager.inject_client(tmp_path, fake)
    # Force detector path: inject client is enough for service ops via manager.get_client
    provider = LSPContextProvider(str(tmp_path), manager=manager, focus_path="calc.py")

    # status() uses detector — may be unavailable; override by ensuring client used
    # Make status available by monkeypatching service.status via fake diagnostics path:
    # When status not AVAILABLE, context shows unavailable. Inject detection:
    from backend.app.lsp.detector import LanguageDetection
    from backend.app.lsp.models import LspServerStatus

    manager._detections[str(tmp_path.resolve())] = LanguageDetection(  # noqa: SLF001
        language="python",
        server="FakeLSP",
        status=LspServerStatus.AVAILABLE,
        message="test",
        command="fake",
    )

    text = provider.build_workspace_context()
    assert "## LSP" in text
    assert "Diagnostics:" in text
    assert "oops" in text
    assert "Active file symbols" in text
    assert "@@" not in text


def test_context_manager_includes_lsp(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    manager = LanguageServerManager()
    fake = FakeLanguageServerClient()
    manager.inject_client(tmp_path, fake)
    from backend.app.lsp.detector import LanguageDetection
    from backend.app.lsp.models import LspServerStatus

    manager._detections[str(tmp_path.resolve())] = LanguageDetection(  # noqa: SLF001
        language="python",
        server="FakeLSP",
        status=LspServerStatus.AVAILABLE,
        message="test",
        command="fake",
    )

    from backend.app.context.manager import DefaultContextManager
    from backend.app.llm.messages import Conversation

    cm = DefaultContextManager(
        session_id="sess_lsp",
        workspace_root=str(tmp_path.resolve()),
        budget=ContextBudget.from_context_window(32_000),
        persist=False,
        lsp_context_provider=LSPContextProvider(
            str(tmp_path.resolve()), manager=manager
        ),
    )
    cm.begin_run("fix with lsp")
    parts = cm._assemble(Conversation(), tools=None)  # noqa: SLF001
    assert "## LSP" in parts.lsp_context
