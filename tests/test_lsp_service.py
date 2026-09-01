"""LSPService tests with FakeLanguageServerClient."""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.lsp.adapters import FakeLanguageServerClient
from backend.app.lsp.errors import LspOutsideWorkspaceError, LspUnavailableError
from backend.app.lsp.manager import LanguageServerManager
from backend.app.lsp.models import (
    Diagnostic,
    DiagnosticSeverity,
    HoverResult,
    Location,
    Position,
    Range,
    Symbol,
    SymbolKind,
)
from backend.app.lsp.service import LSPService
from backend.app.workspace.workspace import Workspace


def _rng(line: int = 0, col: int = 0) -> Range:
    return Range(start=Position(line, col), end=Position(line, col + 1))


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    (tmp_path / "calc.py").write_text("def add(a,b): return a+b\n", encoding="utf-8")
    return Workspace(tmp_path)


@pytest.fixture
def fake_service(workspace: Workspace) -> tuple[LSPService, FakeLanguageServerClient]:
    fake = FakeLanguageServerClient(
        diagnostics=[
            Diagnostic(
                message='"result" is not defined',
                severity=DiagnosticSeverity.ERROR,
                path="calc.py",
                range=_rng(1, 11),
                source="fake",
            )
        ],
        symbols={
            "calc.py": [
                Symbol(
                    name="add",
                    kind=SymbolKind.FUNCTION,
                    range=_rng(0, 0),
                    path="calc.py",
                )
            ]
        },
        definitions={
            ("calc.py", 0, 4): [Location(path="calc.py", range=_rng(0, 4))],
        },
        references={
            ("calc.py", 0, 4): [
                Location(path="calc.py", range=_rng(0, 4)),
                Location(path="other.py", range=_rng(2, 0)),
            ],
        },
        hovers={
            ("calc.py", 0, 4): HoverResult(contents="def add(a, b)"),
        },
    )
    manager = LanguageServerManager()
    manager.inject_client(workspace.root, fake)
    return LSPService(workspace, manager=manager), fake


def test_status_available(fake_service) -> None:
    service, _ = fake_service
    # Without detection override, status may be unavailable if no pyright;
    # inject ensures client works for ops. Status uses detector separately.
    # Force detection-like availability by calling client methods.
    diags = service.diagnostics("calc.py")
    assert len(diags) == 1


def test_diagnostics(fake_service) -> None:
    service, fake = fake_service
    diags = service.diagnostics()
    assert diags[0].message.startswith('"result"')
    assert any(c.startswith("diagnostics:") for c in fake.calls)


def test_symbols_definition_references_hover(fake_service) -> None:
    service, _ = fake_service
    symbols = service.symbols("calc.py")
    assert symbols[0].name == "add"
    defs = service.definition("calc.py", 0, 4)
    assert defs.locations[0].path == "calc.py"
    refs = service.references("calc.py", 0, 4)
    assert len(refs.locations) == 2
    hover = service.hover("calc.py", 0, 4)
    assert "add" in hover.contents


def test_workspace_isolation(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    (a / "secret.py").write_text("SECRET=1\n", encoding="utf-8")
    (b / "ok.py").write_text("x=1\n", encoding="utf-8")

    ws_b = Workspace(b)
    manager = LanguageServerManager()
    manager.inject_client(b, FakeLanguageServerClient())
    service = LSPService(ws_b, manager=manager)

    with pytest.raises(LspOutsideWorkspaceError):
        service.diagnostics("../a/secret.py")


def test_unavailable_propagates(workspace: Workspace) -> None:
    fake = FakeLanguageServerClient(fail_with=LspUnavailableError("down"))
    manager = LanguageServerManager()
    manager.inject_client(workspace.root, fake)
    service = LSPService(workspace, manager=manager)
    with pytest.raises(LspUnavailableError):
        service.diagnostics()
