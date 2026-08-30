"""V0.6 Phase 3：Backend API 测试（FastAPI TestClient）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.api.deps import AppState, build_app_state
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.persistence.store import SqliteStore
from backend.app.services.agent_service import AgentService
from backend.app.session.service import SessionService


class ScriptedLLMClient(LLMClient):
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.config = LLMConfig(api_key="fake", base_url="http://localhost", model="fake")
        self._client = None  # type: ignore[assignment]
        self._queue = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        conversation: Conversation,
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        self.calls.append({"messages": conversation.to_api_messages(), "tools": tools})
        if not self._queue:
            raise LLMRequestError("无更多脚本响应")
        return self._queue.pop(0)


@pytest.fixture
def api_env(tmp_path: Path) -> tuple[TestClient, Path, ScriptedLLMClient]:
    ws = tmp_path / "workspace"
    ws.mkdir()
    db_path = tmp_path / "api.db"
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="call_1",
                        name="calculator",
                        arguments={"expression": "2+2"},
                        arguments_raw='{"expression":"2+2"}',
                    ),
                ),
            ),
            LLMResponse(content="等于 4", tool_calls=()),
            LLMResponse(content="第二轮", tool_calls=()),
        ]
    )
    state = build_app_state(db_path=db_path, llm=llm, max_steps=8)
    app = create_app(state=state)
    client = TestClient(app)
    return client, ws, llm


def test_health(api_env: tuple[TestClient, Path, ScriptedLLMClient]) -> None:
    client, _ws, _llm = api_env
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "ok"
    assert body["app"] == "CodeWisp"
    assert "version" in body


def test_session_crud(api_env: tuple[TestClient, Path, ScriptedLLMClient]) -> None:
    client, ws, _llm = api_env
    create = client.post(
        "/api/sessions",
        json={
            "title": "Fix bug",
            "workspace": str(ws),
            "provider_id": "deepseek",
            "model_id": "deepseek-chat",
        },
    )
    assert create.status_code == 201
    body = create.json()
    sid = body["session_id"]
    assert body["workspace"] == str(ws.resolve())
    assert body["provider_id"] == "deepseek"

    listed = client.get("/api/sessions")
    assert listed.status_code == 200
    assert any(s["session_id"] == sid for s in listed.json())

    got = client.get(f"/api/sessions/{sid}")
    assert got.status_code == 200
    assert got.json()["title"] == "Fix bug"

    patched = client.patch(f"/api/sessions/{sid}", json={"title": "Fix auth"})
    assert patched.status_code == 200
    assert patched.json()["title"] == "Fix auth"

    deleted = client.delete(f"/api/sessions/{sid}")
    assert deleted.status_code == 204
    assert client.get(f"/api/sessions/{sid}").status_code == 404
    assert client.get(f"/api/sessions/{sid}").json()["error"] == "SESSION_NOT_FOUND"


def test_post_message_runs_agent_and_get_messages(
    api_env: tuple[TestClient, Path, ScriptedLLMClient],
) -> None:
    client, ws, llm = api_env
    sid = client.post(
        "/api/sessions",
        json={"title": "calc", "workspace": str(ws)},
    ).json()["session_id"]

    post = client.post(
        f"/api/sessions/{sid}/messages",
        json={"content": "算 2+2"},
    )
    assert post.status_code == 200
    data = post.json()
    assert data["status"] == "completed"
    assert data["termination_reason"] == "completed"
    assert data["final_answer"] == "等于 4"
    assert data["run"]["provider_id"] == "deepseek"
    assert data["run"]["model_id"] == "deepseek-chat"
    assert len(data["steps"]) == 2
    assert any(m["role"] == "tool" for m in data["messages"])
    assert any(
        m["role"] == "assistant" and m.get("tool_calls")
        for m in data["messages"]
    )

    messages = client.get(f"/api/sessions/{sid}/messages")
    assert messages.status_code == 200
    roles = [m["role"] for m in messages.json()]
    assert roles[0] == "system"
    assert "user" in roles and "tool" in roles
    tool = next(m for m in messages.json() if m["role"] == "tool")
    assert tool["tool_call_id"] == "call_1"
    assert tool["step_id"] is not None

    # 确认走的是注入的 ScriptedLLM，而不是真实网络
    assert len(llm.calls) >= 2


def test_invalid_workspace_and_message(
    api_env: tuple[TestClient, Path, ScriptedLLMClient],
) -> None:
    client, ws, _llm = api_env
    bad = client.post(
        "/api/sessions",
        json={"title": "x", "workspace": str(ws / "missing")},
    )
    assert bad.status_code == 400
    assert bad.json()["error"] == "INVALID_WORKSPACE"

    sid = client.post(
        "/api/sessions",
        json={"title": "ok", "workspace": str(ws)},
    ).json()["session_id"]
    empty = client.post(f"/api/sessions/{sid}/messages", json={"content": "   "})
    # pydantic min_length=1 可能先拦；空格通过 pydantic 后由领域层拒绝
    assert empty.status_code in {400, 422}
    if empty.status_code == 400:
        assert empty.json()["error"] == "INVALID_MESSAGE"


def test_api_uses_agent_service_not_second_loop(tmp_path: Path) -> None:
    """烟雾：create_app 组装的 agents 是 AgentService 实例。"""
    ws = tmp_path / "w"
    ws.mkdir()
    llm = ScriptedLLMClient(
        [LLMResponse(content="hi", tool_calls=(), finish_reason="stop")]
    )
    state = build_app_state(db_path=tmp_path / "x.db", llm=llm)
    assert isinstance(state.agents, AgentService)
    assert isinstance(state.sessions, SessionService)
    assert isinstance(state.store, SqliteStore)
    assert state.permission_broker is not None
    assert state.model_resolver is not None

    app = create_app(state=state)
    client = TestClient(app)
    sid = client.post(
        "/api/sessions",
        json={"title": "t", "workspace": str(ws)},
    ).json()["session_id"]
    resp = client.post(f"/api/sessions/{sid}/messages", json={"content": "hello"})
    assert resp.status_code == 200
    assert resp.json()["final_answer"] == "hi"
    assert isinstance(resp.json().get("events"), list)
    assert any(e["event_type"] == "agent_completed" for e in resp.json()["events"])


def test_api_list_providers_and_models(
    api_env: tuple[TestClient, Path, ScriptedLLMClient],
) -> None:
    client, _ws, _llm = api_env
    providers = client.get("/api/providers")
    assert providers.status_code == 200
    body = providers.json()
    assert any(p["provider_id"] == "deepseek" for p in body)

    models = client.get("/api/models")
    assert models.status_code == 200
    assert any(m["model_id"] == "deepseek-chat" for m in models.json())

    filtered = client.get("/api/models", params={"provider_id": "deepseek"})
    assert filtered.status_code == 200
    assert all(m["provider_id"] == "deepseek" for m in filtered.json())


def test_api_permission_pending_empty(
    api_env: tuple[TestClient, Path, ScriptedLLMClient],
) -> None:
    client, ws, _llm = api_env
    sid = client.post(
        "/api/sessions",
        json={"title": "p", "workspace": str(ws)},
    ).json()["session_id"]
    pending = client.get(f"/api/sessions/{sid}/permissions/pending")
    assert pending.status_code == 200
    assert pending.json()["pending"] is None


def test_api_permission_broker_allow(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """POST message 阻塞在 ASK；另一线程 decide allow 后继续。"""
    import threading
    import time

    from backend.app.execution.request import ExecutionRequest
    from backend.app.execution.result import ExecutionResult
    from backend.app.execution.service import ExecutionService

    def fake_run(self: ExecutionService, request: ExecutionRequest) -> ExecutionResult:
        return ExecutionResult(
            success=True,
            exit_code=0,
            stdout="installed",
            stderr="",
            duration_ms=1.0,
            command=request.command,
            args=list(request.args),
            cwd=str(request.cwd),
        )

    monkeypatch.setattr(ExecutionService, "run", fake_run)

    ws = tmp_path / "ws"
    ws.mkdir()
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="run_command",
                        arguments={"command": "npm", "args": ["install"]},
                        arguments_raw='{"command":"npm","args":["install"]}',
                    ),
                ),
            ),
            LLMResponse(content="done after allow", tool_calls=()),
        ]
    )
    state = build_app_state(db_path=tmp_path / "perm.db", llm=llm, max_steps=8)
    app = create_app(state=state)
    client = TestClient(app)
    sid = client.post(
        "/api/sessions",
        json={"title": "ask", "workspace": str(ws)},
    ).json()["session_id"]

    result_box: dict[str, Any] = {}

    def decide_worker() -> None:
        for _ in range(80):
            pending = client.get(f"/api/sessions/{sid}/permissions/pending").json()
            if pending.get("pending"):
                req = pending["pending"]
                time.sleep(0.05)
                decide = client.post(
                    f"/api/sessions/{sid}/permissions/decide",
                    json={"request_id": req["request_id"], "decision": "allow"},
                )
                result_box["decide_status"] = decide.status_code
                return
            time.sleep(0.05)
        result_box["decide_status"] = "timeout"

    t = threading.Thread(target=decide_worker, daemon=True)
    t.start()
    post = client.post(
        f"/api/sessions/{sid}/messages",
        json={"content": "please npm install"},
    )
    t.join(timeout=15)
    assert post.status_code == 200
    data = post.json()
    assert data["status"] == "completed"
    assert data["final_answer"] == "done after allow"
    assert result_box.get("decide_status") == 200
    types = [e["event_type"] for e in data["events"]]
    assert "permission_requested" in types
    assert "permission_resolved" in types
