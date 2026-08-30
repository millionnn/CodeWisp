"""AgentService + ModelResolver 集成测试（mock LLM，无真实 API）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.app.agent.state import AgentStatus
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse
from backend.app.persistence.store import SqliteStore
from backend.app.providers.model import Model
from backend.app.providers.provider import Provider
from backend.app.providers.resolver import ModelResolver
from backend.app.services.agent_service import AgentService
from backend.app.session.service import SessionService


class ScriptedLLMClient(LLMClient):
    def __init__(self, responses: list[LLMResponse], *, model: str) -> None:
        self.config = LLMConfig(
            api_key="fake",
            base_url="http://localhost",
            model=model,
        )
        self._client = None  # type: ignore[assignment]
        self._queue = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        conversation: Conversation,
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {
                "messages": conversation.to_api_messages(),
                "tools": tools,
                "model": self.config.model,
            }
        )
        if not self._queue:
            raise LLMRequestError("无更多脚本响应")
        return self._queue.pop(0)


@pytest.fixture
def db_workspace(tmp_path: Path) -> tuple[SqliteStore, Path]:
    ws = tmp_path / "project"
    ws.mkdir()
    store = SqliteStore(tmp_path / "codewisp.db")
    store.connect()
    return store, ws


def _resolver_with_tracking(
    monkeypatch: pytest.MonkeyPatch,
) -> tuple[ModelResolver, dict[str, list[str]]]:
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    seen: dict[str, list[str]] = {"models": []}

    def factory(provider: Provider, model: Model, config: LLMConfig) -> LLMClient:
        seen["models"].append(f"{provider.provider_id}/{model.model_id}:{config.model}")
        return ScriptedLLMClient(
            [LLMResponse(content=f"ok:{config.model}", finish_reason="stop")],
            model=config.model,
        )

    return ModelResolver.create_default(client_factory=factory), seen


def test_session_a_b_resolve_different_identities(
    db_workspace: tuple[SqliteStore, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws = db_workspace
    resolver, seen = _resolver_with_tracking(monkeypatch)
    agents = AgentService(store, model_resolver=resolver, max_steps=3)
    sessions = agents.sessions

    session_a = sessions.create_session(
        title="A",
        workspace=ws,
        provider_id="deepseek",
        model_id="deepseek-chat",
    )
    session_b = sessions.create_session(
        title="B",
        workspace=ws,
        provider_id="openai",
        model_id="gpt-4o",
    )

    result_a = agents.run(session_a.session_id, "hi-a")
    result_b = agents.run(session_b.session_id, "hi-b")

    assert result_a.run.provider_id == "deepseek"
    assert result_a.run.model_id == "deepseek-chat"
    assert result_a.state.final_answer == "ok:deepseek-chat"

    assert result_b.run.provider_id == "openai"
    assert result_b.run.model_id == "gpt-4o"
    assert result_b.state.final_answer == "ok:gpt-4o"

    assert "deepseek/deepseek-chat:deepseek-chat" in seen["models"]
    assert "openai/gpt-4o:gpt-4o" in seen["models"]


def test_agent_run_snapshot_from_resolved_identity(
    db_workspace: tuple[SqliteStore, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws = db_workspace
    resolver, _ = _resolver_with_tracking(monkeypatch)
    agents = AgentService(store, model_resolver=resolver)
    session = agents.sessions.create_session(
        title="snap",
        workspace=ws,
        provider_id="deepseek",
        model_id="deepseek-chat",
    )
    result = agents.run(session.session_id, "ping")
    assert result.run.provider_id == session.provider_id
    assert result.run.model_id == session.model_id
    assert result.state.status == AgentStatus.COMPLETED


def test_session_model_change_keeps_old_run_snapshot(
    db_workspace: tuple[SqliteStore, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws = db_workspace
    resolver, seen = _resolver_with_tracking(monkeypatch)
    agents = AgentService(store, model_resolver=resolver)
    session = agents.sessions.create_session(
        title="mutate",
        workspace=ws,
        provider_id="deepseek",
        model_id="deepseek-chat",
    )
    first = agents.run(session.session_id, "first")
    assert first.run.model_id == "deepseek-chat"

    agents.sessions.update_session(
        session.session_id,
        provider_id="openai",
        model_id="gpt-4o-mini",
    )
    second = agents.run(session.session_id, "second")

    assert first.run.provider_id == "deepseek"
    assert first.run.model_id == "deepseek-chat"
    assert second.run.provider_id == "openai"
    assert second.run.model_id == "gpt-4o-mini"

    # 旧 Run 行未被改写
    stored_first = agents.sessions.runs.get_run(first.run.agent_run_id)
    assert stored_first.provider_id == "deepseek"
    assert stored_first.model_id == "deepseek-chat"
    assert seen["models"][-1].endswith("gpt-4o-mini:gpt-4o-mini")


def test_v06_compatibility_fixed_llm_still_works(
    db_workspace: tuple[SqliteStore, Path],
) -> None:
    """不传 ModelResolver、只传固定 llm 时，行为与 V0.6 一致。"""
    store, ws = db_workspace
    llm = ScriptedLLMClient(
        [LLMResponse(content="legacy", finish_reason="stop")],
        model="fake",
    )
    agents = AgentService(store, llm=llm)
    session = agents.sessions.create_session(
        title="legacy",
        workspace=ws,
        provider_id="deepseek",
        model_id="deepseek-chat",
    )
    result = agents.run(session.session_id, "hello")
    assert result.state.final_answer == "legacy"
    assert result.run.provider_id == "deepseek"
    assert result.run.model_id == "deepseek-chat"


def test_resolve_model_helper(
    db_workspace: tuple[SqliteStore, Path],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store, ws = db_workspace
    resolver, _ = _resolver_with_tracking(monkeypatch)
    agents = AgentService(store, model_resolver=resolver)
    session = agents.sessions.create_session(
        title="helper",
        workspace=ws,
        provider_id="openai",
        model_id="gpt-4o",
    )
    resolved = agents.resolve_model(session)
    assert resolved is not None
    assert resolved.model_id == "gpt-4o"
