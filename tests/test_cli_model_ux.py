"""V0.7 Phase 3：CLI Provider/Model UX 与 Session 隔离测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

from backend.app.cli.interface import run_cli
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse
from backend.app.persistence.store import SqliteStore
from backend.app.providers.model import Model
from backend.app.providers.provider import Provider
from backend.app.providers.resolver import ModelResolver
from backend.app.services.agent_service import AgentService


class ScriptedLLMClient(LLMClient):
    def __init__(self, responses: list[LLMResponse], *, model: str = "fake") -> None:
        self.config = LLMConfig(api_key="fake", base_url="http://localhost", model=model)
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
            {"messages": conversation.to_api_messages(), "model": self.config.model}
        )
        if not self._queue:
            raise LLMRequestError("无更多脚本响应")
        return self._queue.pop(0)


def _make_agents(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> tuple[AgentService, Path]:
    monkeypatch.setenv("LLM_API_KEY", "sk-test")
    ws = tmp_path / "ws"
    ws.mkdir()
    store = SqliteStore(tmp_path / "cli.db")
    store.connect()

    def factory(provider: Provider, model: Model, config: LLMConfig) -> LLMClient:
        return ScriptedLLMClient(
            [LLMResponse(content=f"via:{config.model}", finish_reason="stop")],
            model=config.model,
        )

    resolver = ModelResolver.create_default(client_factory=factory)
    agents = AgentService(store, model_resolver=resolver, max_steps=5)
    return agents, ws


def test_cli_help_and_providers_models(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    agents, ws = _make_agents(tmp_path, monkeypatch)
    outputs: list[str] = []
    inputs = iter(["/help", "/providers", "/models", "/model", "q", "/status", "/exit"])
    code = run_cli(
        agents,
        workspace_root=ws,
        input_fn=lambda _p: next(inputs),
        output_fn=outputs.append,
        show_tool_trace=False,
    )
    assert code == 0
    blob = "\n".join(outputs)
    assert "/providers" in blob and "/model" in blob
    assert "Available Providers" in blob
    assert "deepseek" in blob and "openai" in blob
    assert "Available Models" in blob
    assert "deepseek-chat" in blob
    assert "选择模型" in blob
    assert "CodeWisp Status" in blob
    assert "Resolver" in blob and "configured" in blob


def test_cli_model_switch_persists_and_new_run_uses_it(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agents, ws = _make_agents(tmp_path, monkeypatch)
    outputs: list[str] = []
    inputs = iter(
        [
            "/model openai gpt-4o",
            "hello after switch",
            "/exit",
        ]
    )
    code = run_cli(
        agents,
        workspace_root=ws,
        session_title="switch-me",
        input_fn=lambda _p: next(inputs),
        output_fn=outputs.append,
        show_tool_trace=False,
    )
    assert code == 0
    assert any("已切换模型: openai/gpt-4o" in line for line in outputs)
    assert any("via:gpt-4o" in line for line in outputs)

    sessions = agents.sessions.list_sessions()
    assert len(sessions) == 1
    assert sessions[0].provider_id == "openai"
    assert sessions[0].model_id == "gpt-4o"
    runs = agents.sessions.list_runs(sessions[0].session_id)
    assert len(runs) == 1
    assert runs[0].provider_id == "openai"
    assert runs[0].model_id == "gpt-4o"


def test_cli_invalid_model_does_not_mutate_session(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agents, ws = _make_agents(tmp_path, monkeypatch)
    outputs: list[str] = []
    inputs = iter(["/model totally-unknown-model", "/status", "/exit"])
    code = run_cli(
        agents,
        workspace_root=ws,
        input_fn=lambda _p: next(inputs),
        output_fn=outputs.append,
        show_tool_trace=False,
    )
    assert code == 0
    assert any("Model Error" in line or "未知" in line for line in outputs)
    # 失败后 Session 未改；/status 仍显示原身份
    blob = "\n".join(outputs)
    assert "deepseek" in blob and "deepseek-chat" in blob


def test_cli_session_model_isolation(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agents, ws = _make_agents(tmp_path, monkeypatch)
    outputs: list[str] = []
    step = {"n": 0}
    ids: dict[str, str] = {}

    def input_fn(_p: str) -> str | None:
        n = step["n"]
        step["n"] += 1
        if n == 0:
            return "task-a"
        if n == 1:
            for s in agents.sessions.list_sessions():
                if s.title == "Session A":
                    ids["a"] = s.session_id
                    break
            return "/new --provider-id openai --model-id gpt-4o Session B"
        if n == 2:
            return "task-b"
        if n == 3:
            return "/sessions"
        if n == 4:
            return f"/use {ids['a']}"
        if n == 5:
            return "/status"
        return "/exit"

    code = run_cli(
        agents,
        workspace_root=ws,
        session_title="Session A",
        input_fn=input_fn,
        output_fn=outputs.append,
        show_tool_trace=False,
    )
    assert code == 0
    # A 仍为 deepseek；B 为 openai
    by_title = {s.title: s for s in agents.sessions.list_sessions()}
    assert by_title["Session A"].provider_id == "deepseek"
    assert by_title["Session A"].model_id == "deepseek-chat"
    assert by_title["Session B"].provider_id == "openai"
    assert by_title["Session B"].model_id == "gpt-4o"
    # /use A 后 /status 显示 deepseek
    assert "deepseek" in "\n".join(outputs)
    runs_a = agents.sessions.list_runs(by_title["Session A"].session_id)
    runs_b = agents.sessions.list_runs(by_title["Session B"].session_id)
    assert runs_a[0].model_id == "deepseek-chat"
    assert runs_b[0].model_id == "gpt-4o"


def test_cli_model_switch_keeps_old_run_snapshot(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    agents, ws = _make_agents(tmp_path, monkeypatch)
    outputs: list[str] = []
    inputs = iter(
        [
            "first",
            "/model openai gpt-4o-mini",
            "second",
            "/exit",
        ]
    )
    code = run_cli(
        agents,
        workspace_root=ws,
        input_fn=lambda _p: next(inputs),
        output_fn=outputs.append,
        show_tool_trace=False,
    )
    assert code == 0
    session = agents.sessions.list_sessions()[0]
    runs = agents.sessions.list_runs(session.session_id)
    assert len(runs) == 2
    assert runs[0].provider_id == "deepseek"
    assert runs[0].model_id == "deepseek-chat"
    assert runs[1].provider_id == "openai"
    assert runs[1].model_id == "gpt-4o-mini"


def test_render_trace_permission_and_tools() -> None:
    from backend.app.agent.events import AgentEvent
    from backend.app.agent.state import AgentState, AgentStatus
    from backend.app.cli.trace import render_agent_trace
    from backend.app.session.models import AgentRun

    state = AgentState(status=AgentStatus.PERMISSION_REQUIRED, step=1, max_steps=5)
    state.termination_reason = "permission_required"
    state.events = [
        AgentEvent(event_type="llm_called", step=1, metadata={}),
        AgentEvent(
            event_type="tool_called",
            step=1,
            tool_name="run_command",
            metadata={"arguments": {"command": "rm -rf /"}},
        ),
        AgentEvent(
            event_type="permission_required",
            step=1,
            tool_name="run_command",
            metadata={"error": "ASK required"},
        ),
    ]
    run = AgentRun.create(
        session_id="ses_x",
        provider_id="deepseek",
        model_id="deepseek-chat",
    )
    lines: list[str] = []
    render_agent_trace(state, run, output_fn=lines.append)
    blob = "\n".join(lines)
    assert "◇ run_command" in blob
    assert "Permission required" in blob
    assert "permission required" in blob.lower() or "Permission required" in blob or "stopped (permission)" in blob
