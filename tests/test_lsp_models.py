"""LSP domain model tests."""

from __future__ import annotations

from backend.app.lsp.models import (
    DefinitionResult,
    Diagnostic,
    DiagnosticSeverity,
    HoverResult,
    Location,
    Position,
    Range,
    ReferenceResult,
    Symbol,
    SymbolKind,
)


def _rng(line: int = 0, col: int = 0) -> Range:
    return Range(start=Position(line, col), end=Position(line, col + 1))


def test_diagnostic_roundtrip() -> None:
    d = Diagnostic(
        message="undefined name",
        severity=DiagnosticSeverity.ERROR,
        source="pyright",
        range=_rng(10, 4),
        code="reportUndefinedVariable",
        path="calc.py",
    )
    restored = Diagnostic.from_dict(d.to_dict())
    assert restored.message == d.message
    assert restored.severity is DiagnosticSeverity.ERROR
    assert restored.path == "calc.py"
    assert "Line 11:5" in restored.render_line()


def test_location_and_definition_roundtrip() -> None:
    loc = Location(path="a.py", range=_rng(1, 2), uri="file:///a.py")
    result = DefinitionResult(locations=[loc])
    data = result.to_dict()
    restored = DefinitionResult.from_dict(data)
    assert restored.locations[0].path == "a.py"


def test_reference_roundtrip() -> None:
    result = ReferenceResult(
        locations=[Location(path="b.py", range=_rng(3, 0))]
    )
    assert ReferenceResult.from_dict(result.to_dict()).locations[0].path == "b.py"


def test_symbol_tree_and_roundtrip() -> None:
    child = Symbol(
        name="add",
        kind=SymbolKind.METHOD,
        range=_rng(5, 4),
        path="c.py",
    )
    parent = Symbol(
        name="Calculator",
        kind=SymbolKind.CLASS,
        range=_rng(1, 0),
        children=[child],
        path="c.py",
    )
    restored = Symbol.from_dict(parent.to_dict())
    assert restored.children[0].name == "add"
    tree = "\n".join(parent.render_tree())
    assert "Calculator" in tree
    assert "add()" in tree


def test_hover_roundtrip() -> None:
    h = HoverResult(contents="(function) add", range=_rng())
    assert HoverResult.from_dict(h.to_dict()).contents == "(function) add"


def test_severity_from_lsp_int() -> None:
    assert DiagnosticSeverity.from_lsp_int(1) is DiagnosticSeverity.ERROR
    assert DiagnosticSeverity.from_lsp_int(2) is DiagnosticSeverity.WARNING
