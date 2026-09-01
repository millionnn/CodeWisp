"""MCP Agent integration + graceful degradation."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

import pytest

from backend.app.agent.event_sink import RecordingEventSink
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.mcp.client import FakeMCPClient
from backend.app.mcp.config import write_example_workspace_mcp_config
from backend.app.mcp.manager import MCPManager, reset_managers_for_tests
from backend.app.mcp.models import MCPPermissionLevel, MCPServerConfig, MCPToolInfo
from backend.app.mcp.registry import sync_mcp_tools_to_registry
from backend.app.persistence.store import SqliteStore
from backend.app.services.agent_service import AgentService
from backend.app.tools.registry import ToolRegistry


class ScriptedLLM(LLMClient):
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
            raise LLMRequestError("no more scripted responses")
        return self._queue.pop(0)


@pytest.fixture(autouse=True)
def _reset_mcp() -> None:
    reset_managers_for_tests()
    yield
    reset_managers_for_tests()


def test_agent_selects_mcp_tool_and_continues(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "t.db")
    store.connect()
    info = MCPToolInfo(
        server_id="demo",
        tool_name="search_project_docs",
        description="Search docs",
        permission_level=MCPPermissionLevel.ALLOW,
        input_schema={
            "type": "object",
            "properties": {"query": {"type": "string"}},
            "required": ["query"],
        },
    )
    fake = FakeMCPClient(
        "demo",
        [info],
        call_handler=lambda name, args: f"Found docs for {args.get('query')}",
    )
    mgr = MCPManager(
        workspace_root=tmp_path,
        configs={"demo": MCPServerConfig(server_id="demo", command="fake")},
    )
    mgr.inject_client("demo", fake)

    llm = ScriptedLLM(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="mcp.demo.search_project_docs",
                        arguments={"query": "bug"},
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content="Fixed via MCP docs. Tests: ok",
                tool_calls=(),
                finish_reason="stop",
            ),
        ]
    )
    agents = AgentService(store, llm=llm)
    session = agents.sessions.create_session(
        title="mcp-agent",
        workspace=tmp_path,
        provider_id="test",
        model_id="test-model",
    )
    agents._mcp_managers[session.workspace] = mgr

    sink = RecordingEventSink()
    result = agents.run(session.session_id, "Find docs for the bug", event_sink=sink)
    assert result.state.final_answer
    assert "Fixed" in (result.state.final_answer or "")
    tool_names = [
        e.tool_name for e in sink.events if e.event_type == "tool_completed"
    ]
    assert "mcp.demo.search_project_docs" in tool_names


def test_mcp_unavailable_agent_still_runs(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "t.db")
    store.connect()
    mgr = MCPManager(
        workspace_root=tmp_path,
        configs={
            "broken": MCPServerConfig(
                server_id="broken",
                command="__missing_mcp__",
                enabled=True,
            )
        },
    )
    mgr.connect_all_enabled()

    llm = ScriptedLLM(
        [
            LLMResponse(
                content="Answer without MCP",
                tool_calls=(),
                finish_reason="stop",
            )
        ]
    )
    agents = AgentService(store, llm=llm)
    session = agents.sessions.create_session(
        title="mcp-deg",
        workspace=tmp_path,
        provider_id="test",
        model_id="test-model",
    )
    agents._mcp_managers[session.workspace] = mgr
    result = agents.run(session.session_id, "hello")
    assert result.state.final_answer == "Answer without MCP"


def test_session_workspace_isolation(tmp_path: Path) -> None:
    a = tmp_path / "a"
    b = tmp_path / "b"
    a.mkdir()
    b.mkdir()
    demo = Path(__file__).resolve().parents[1] / "backend" / "app" / "mcp" / "demo_server.py"
    write_example_workspace_mcp_config(a, demo)
    mgr_a = MCPManager(workspace_root=a)
    mgr_a.reload_config()
    mgr_b = MCPManager(workspace_root=b)
    mgr_b.reload_config()
    assert "demo" in {s.server_id for s in mgr_a.list_servers()}
    assert mgr_b.list_servers() == []


def test_stdio_demo_sync_into_registry(tmp_path: Path) -> None:
    demo = Path(__file__).resolve().parents[1] / "backend" / "app" / "mcp" / "demo_server.py"
    write_example_workspace_mcp_config(tmp_path, demo)
    cfg_path = tmp_path / ".codewisp" / "mcp.json"
    data = json.loads(cfg_path.read_text(encoding="utf-8"))
    data["mcpServers"]["demo"]["command"] = sys.executable
    cfg_path.write_text(json.dumps(data), encoding="utf-8")

    mgr = MCPManager(workspace_root=tmp_path)
    mgr.reload_config()
    mgr.connect("demo")
    registry = ToolRegistry()
    ids = sync_mcp_tools_to_registry(registry, mgr)
    assert "mcp.demo.search_project_docs" in ids
    assert "mcp.demo.get_project_info" in ids
    tool = registry.get("mcp.demo.search_project_docs")
    out = tool.execute({"query": "MCP"})
    assert out.success
    mgr.disconnect("demo")
