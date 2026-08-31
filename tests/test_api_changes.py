"""V0.9 Change Management API 测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.api.deps import build_app_state
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall


class ScriptedLLMClient(LLMClient):
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.config = LLMConfig(api_key="fake", base_url="http://localhost", model="fake")
        self._client = None  # type: ignore[assignment]
        self._queue = list(responses)

    def chat(
        self,
        conversation: Conversation,
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        if not self._queue:
            raise LLMRequestError("无更多脚本响应")
        return self._queue.pop(0)


@pytest.fixture
def change_api(tmp_path: Path) -> tuple[TestClient, Path, str, str]:
    ws = tmp_path / "ws"
    ws.mkdir()
    (ws / "calc.py").write_text("return a - b\n", encoding="utf-8")
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="tc_api_edit",
                        name="edit_file",
                        arguments={
                            "path": "calc.py",
                            "old_text": "return a - b",
                            "new_text": "return a + b",
                        },
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="fixed", tool_calls=(), finish_reason="stop"),
        ]
    )
    state = build_app_state(db_path=tmp_path / "api.db", llm=llm, max_steps=8)
    app = create_app(state=state)
    client = TestClient(app)
    sid = client.post(
        "/api/sessions",
        json={"title": "chg-api", "workspace": str(ws)},
    ).json()["session_id"]
    post = client.post(f"/api/sessions/{sid}/messages", json={"content": "fix add"})
    assert post.status_code == 200
    run_id = post.json()["run"]["agent_run_id"]
    return client, ws, sid, run_id


def test_api_run_changes_diff_and_step_snapshots(change_api) -> None:
    client, ws, sid, run_id = change_api
    changes = client.get(f"/api/sessions/{sid}/runs/{run_id}/changes")
    assert changes.status_code == 200
    body = changes.json()
    assert len(body) == 1
    assert body[0]["path"] == "calc.py"
    assert body[0]["change_type"] == "MODIFIED"
    step_id = body[0]["agent_step_id"]

    diff = client.get(f"/api/sessions/{sid}/runs/{run_id}/diff")
    assert diff.status_code == 200
    d = diff.json()
    assert d["scope"] == "run"
    assert d["files"][0]["after"] == "return a + b\n"
    assert "return a + b" in d["unified_diff"]

    step_diff = client.get(f"/api/sessions/{sid}/steps/{step_id}/diff")
    assert step_diff.status_code == 200
    assert step_diff.json()["scope"] == "step"

    snaps = client.get(f"/api/sessions/{sid}/steps/{step_id}/snapshots")
    assert snaps.status_code == 200
    s = snaps.json()
    assert s["before"]["reason"] == "pre_step"
    assert s["after"]["reason"] == "post_step"
    before_id = s["before"]["snapshot_id"]

    got = client.get(f"/api/snapshots/{before_id}")
    assert got.status_code == 200
    assert got.json()["files"][0]["content"] == "return a - b\n"


def test_api_revert_step_requires_confirm_then_restores(change_api) -> None:
    client, ws, sid, run_id = change_api
    step_id = client.get(f"/api/sessions/{sid}/runs/{run_id}/changes").json()[0][
        "agent_step_id"
    ]
    assert (ws / "calc.py").read_text(encoding="utf-8") == "return a + b\n"

    denied = client.post(
        f"/api/sessions/{sid}/steps/{step_id}/revert",
        json={"confirm": False},
    )
    assert denied.status_code == 400
    assert denied.json()["error"] == "INVALID_SESSION"

    ok = client.post(
        f"/api/sessions/{sid}/steps/{step_id}/revert",
        json={"confirm": True},
    )
    assert ok.status_code == 200
    body = ok.json()
    assert body["ok"] is True
    assert body["denied"] is False
    assert "calc.py" in body["applied"]
    assert (ws / "calc.py").read_text(encoding="utf-8") == "return a - b\n"


def test_api_revert_run(change_api) -> None:
    client, ws, sid, run_id = change_api
    # 再改回去以便测 run revert（上一个测试可能已 revert；本 fixture 独立）
    assert (ws / "calc.py").read_text(encoding="utf-8") == "return a + b\n"
    resp = client.post(
        f"/api/sessions/{sid}/runs/{run_id}/revert",
        json={"confirm": True},
    )
    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    assert (ws / "calc.py").read_text(encoding="utf-8") == "return a - b\n"


def test_api_snapshot_missing(change_api) -> None:
    client, _ws, _sid, _run = change_api
    resp = client.get("/api/snapshots/snap_does_not_exist")
    assert resp.status_code == 404
    assert resp.json()["error"] == "SNAPSHOT_NOT_FOUND"
