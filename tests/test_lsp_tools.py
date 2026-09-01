"""LSP tool tests."""

from __future__ import annotations

from pathlib import Path

from backend.app.lsp.adapters import FakeLanguageServerClient
from backend.app.lsp.errors import LspUnavailableError
from backend.app.lsp.manager import LanguageServerManager
from backend.app.lsp.models import (
    Diagnostic,
    DiagnosticSeverity,
    Location,
    Position,
    Range,
    Symbol,
    SymbolKind,
)
from backend.app.lsp.service import LSPService
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry
from backend.app.workspace.workspace import Workspace


def _rng(line: int = 0, col: int = 0) -> Range:
    return Range(start=Position(line, col), end=Position(line, col + 1))


def _executor(tmp_path: Path, fake: FakeLanguageServerClient) -> ToolExecutor:
    (tmp_path / "calc.py").write_text("def add(a,b): return a+b\n", encoding="utf-8")
    ws = Workspace(tmp_path)
    manager = LanguageServerManager()
    manager.inject_client(tmp_path, fake)
    service = LSPService(ws, manager=manager)
    return ToolExecutor(create_default_registry(workspace=ws, lsp_service=service))


def test_lsp_tools_registered(tmp_path: Path) -> None:
    (tmp_path / "a.py").write_text("x=1\n", encoding="utf-8")
    names = {
        t["function"]["name"]
        for t in create_default_registry(workspace=Workspace(tmp_path)).list_schemas()
    }
    assert {
        "lsp_diagnostics",
        "lsp_definition",
        "lsp_references",
        "lsp_symbols",
        "lsp_hover",
    }.issubset(names)


def test_lsp_diagnostics_tool(tmp_path: Path) -> None:
    fake = FakeLanguageServerClient(
        diagnostics=[
            Diagnostic(
                message="bad",
                severity=DiagnosticSeverity.ERROR,
                path="calc.py",
                range=_rng(1, 0),
            )
        ]
    )
    ex = _executor(tmp_path, fake)
    result = ex.execute("lsp_diagnostics", {"path": "calc.py"})
    assert result.success
    assert result.output["errors"] == 1


def test_lsp_symbols_definition_references_hover(tmp_path: Path) -> None:
    fake = FakeLanguageServerClient(
        symbols={
            "calc.py": [
                Symbol(name="add", kind=SymbolKind.FUNCTION, range=_rng(), path="calc.py")
            ]
        },
        definitions={("calc.py", 0, 4): [Location(path="calc.py", range=_rng())]},
        references={("calc.py", 0, 4): [Location(path="calc.py", range=_rng())]},
    )
    ex = _executor(tmp_path, fake)
    assert ex.execute("lsp_symbols", {"path": "calc.py"}).success
    assert ex.execute(
        "lsp_definition", {"path": "calc.py", "line": 0, "character": 4}
    ).success
    assert ex.execute(
        "lsp_references", {"path": "calc.py", "line": 0, "character": 4}
    ).success
    assert ex.execute(
        "lsp_hover", {"path": "calc.py", "line": 0, "character": 4}
    ).success


def test_lsp_unavailable_does_not_crash(tmp_path: Path) -> None:
    fake = FakeLanguageServerClient(fail_with=LspUnavailableError("no server"))
    ex = _executor(tmp_path, fake)
    result = ex.execute("lsp_diagnostics", {})
    assert result.success is False
    assert result.metadata.get("lsp_unavailable") is True
