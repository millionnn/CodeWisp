"""Git API route tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.api.deps import build_app_state
from tests.git_helpers import git_commit_all, init_git_repo


@pytest.fixture
def git_client(tmp_path: Path) -> tuple[TestClient, str]:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_git_repo(repo)
    (repo / "app.py").write_text("x=1\n", encoding="utf-8")
    git_commit_all(repo, "add app")

    db = tmp_path / "test.db"
    state = build_app_state(db_path=db)
    app = create_app(state=state)
    client = TestClient(app)

    resp = client.post(
        "/api/sessions",
        json={"title": "git test", "workspace": str(repo)},
    )
    assert resp.status_code == 201
    session_id = resp.json()["session_id"]
    return client, session_id


def test_api_git_status(git_client: tuple[TestClient, str]) -> None:
    client, sid = git_client
    resp = client.get(f"/api/sessions/{sid}/git/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_git_repository"] is True
    assert data["branch"] is not None


def test_api_git_diff(git_client: tuple[TestClient, str]) -> None:
    client, sid = git_client
    resp = client.get(f"/api/sessions/{sid}/git/diff")
    assert resp.status_code == 200
    assert "files" in resp.json()


def test_api_git_log(git_client: tuple[TestClient, str]) -> None:
    client, sid = git_client
    resp = client.get(f"/api/sessions/{sid}/git/log?limit=5")
    assert resp.status_code == 200
    assert resp.json()["count"] >= 1


def test_api_git_branches(git_client: tuple[TestClient, str]) -> None:
    client, sid = git_client
    resp = client.get(f"/api/sessions/{sid}/git/branches")
    assert resp.status_code == 200
    assert len(resp.json()["branches"]) >= 1


def test_api_git_commit_requires_confirm(git_client: tuple[TestClient, str], tmp_path: Path) -> None:
    client, sid = git_client
    repo = tmp_path / "repo"
    (repo / "new.py").write_text("y\n", encoding="utf-8")

    resp = client.post(
        f"/api/sessions/{sid}/git/commit",
        json={"message": "feat: add", "paths": ["new.py"], "confirm": False},
    )
    assert resp.status_code == 400 or resp.status_code == 422

    resp2 = client.post(
        f"/api/sessions/{sid}/git/commit",
        json={"message": "feat: add", "paths": ["new.py"], "confirm": True},
    )
    assert resp2.status_code == 200
    assert resp2.json()["ok"] is True
    assert resp2.json()["commit_id"]
