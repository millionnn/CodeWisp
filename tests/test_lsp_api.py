"""LSP API route tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.api.deps import build_app_state
from backend.app.lsp.adapters import FakeLanguageServerClient
from backend.app.lsp.detector import LanguageDetection
from backend.app.lsp.models import (
    Diagnostic,
    DiagnosticSeverity,
    LspServerStatus,
    Position,
    Range,
    Symbol,
    SymbolKind,
)


@pytest.fixture
def lsp_client(tmp_path: Path) -> tuple[TestClient, str, object]:
    repo = tmp_path / "repo"
    repo.mkdir()
    (repo / "calc.py").write_text("def add(a,b): return a+b\n", encoding="utf-8")

    db = tmp_path / "test.db"
    state = build_app_state(db_path=db)
    fake = FakeLanguageServerClient(
        diagnostics=[
            Diagnostic(
                message="warn",
                severity=DiagnosticSeverity.WARNING,
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
    state.agents._lsp_manager.inject_client(repo, fake)  # noqa: SLF001
    state.agents._lsp_manager._detections[str(repo.resolve())] = LanguageDetection(  # noqa: SLF001
        language="python",
        server="FakeLSP",
        status=LspServerStatus.AVAILABLE,
        message="test",
        command="fake",
    )

    app = create_app(state=state)
    client = TestClient(app)
    resp = client.post(
        "/api/sessions",
        json={"title": "lsp test", "workspace": str(repo)},
    )
    assert resp.status_code == 201
    return client, resp.json()["session_id"], state


def test_api_lsp_status(lsp_client) -> None:
    client, sid, _ = lsp_client
    resp = client.get(f"/api/sessions/{sid}/lsp/status")
    assert resp.status_code == 200
    assert resp.json()["language"] == "python"
    assert resp.json()["available"] is True


def test_api_lsp_diagnostics_and_symbols(lsp_client) -> None:
    client, sid, _ = lsp_client
    d = client.get(f"/api/sessions/{sid}/lsp/diagnostics", params={"path": "calc.py"})
    assert d.status_code == 200
    assert d.json()["count"] == 1

    s = client.get(f"/api/sessions/{sid}/lsp/symbols", params={"path": "calc.py"})
    assert s.status_code == 200
    assert s.json()["symbols"][0]["name"] == "add"


def test_api_lsp_definition_references_hover(lsp_client) -> None:
    client, sid, _ = lsp_client
    for endpoint in ("definition", "references", "hover"):
        resp = client.get(
            f"/api/sessions/{sid}/lsp/{endpoint}",
            params={"path": "calc.py", "line": 0, "character": 4},
        )
        assert resp.status_code == 200, endpoint
