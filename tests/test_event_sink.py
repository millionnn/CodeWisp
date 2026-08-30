"""V0.8：EventSink 实时事件与 AgentService 边界。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.agent.event_sink import NullEventSink, RecordingEventSink
from backend.app.agent.loop import AgentLoop
from backend.app.agent.state import AgentStatus
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.persistence.store import SqliteStore
from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.handler import ScriptedPermissionHandler
from backend.app.services.agent_service import AgentService
from backend.app.session.service import SessionService
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry
from backend.app.workspace.workspace import Workspace


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


def test_event_sink_receives_live_events(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    (tmp_path / "a.py").write_text("x = 1\n", encoding="utf-8")
    registry = create_default_registry(workspace=ws)
    executor = ToolExecutor(registry)
    sink = RecordingEventSink()
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="read_file",
                        arguments={"path": "a.py"},
                        arguments_raw='{"path":"a.py"}',
                    ),
                ),
            ),
            LLMResponse(content="已读取", tool_calls=()),
        ]
    )
    state = AgentLoop(
        llm, executor, registry, max_steps=5, event_sink=sink
    ).run("read a.py")
    assert state.status == AgentStatus.COMPLETED
    types = [e.event_type for e in sink.events]
    assert "agent_started" in types
    assert "llm_started" in types
    assert "llm_called" in types
    assert "tool_called" in types
    assert "tool_completed" in types
    assert "agent_completed" in types
    assert "answer_delta" in types
    # sink 不影响结果
    assert state.final_answer == "已读取"
    # answer_delta 只进 sink，不进 state.events
    assert [e.event_type for e in state.events] == [
        t for t in types if t != "answer_delta"
    ]


def test_event_sink_none_behaves_normally(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    registry = create_default_registry(workspace=ws)
    executor = ToolExecutor(registry)
    llm = ScriptedLLMClient(
        [LLMResponse(content="ok", tool_calls=())]
    )
    state = AgentLoop(llm, executor, registry, max_steps=3).run("hi")
    assert state.status == AgentStatus.COMPLETED
    assert any(e.event_type == "agent_completed" for e in state.events)


def test_null_event_sink_noop() -> None:
    NullEventSink().emit(
        __import__("backend.app.agent.events", fromlist=["AgentEvent"]).AgentEvent(
            event_type="agent_started", step=0
        )
    )


def test_agent_service_event_sink_and_permission(
    tmp_path: Path,
) -> None:
    store = SqliteStore(tmp_path / "db.sqlite")
    store.connect()
    sessions = SessionService(store)
    session = sessions.create_session(
        title="v08",
        workspace=tmp_path,
        provider_id="deepseek",
        model_id="deepseek-chat",
    )
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
            LLMResponse(content="denied noted", tool_calls=()),
        ]
    )
    sink = RecordingEventSink()
    handler = ScriptedPermissionHandler([PermissionDecision.DENY])
    agents = AgentService(store, llm=llm, max_steps=5)
    result = agents.run(
        session.session_id,
        "npm install",
        event_sink=sink,
        permission_handler=handler,
    )
    assert result.state.status == AgentStatus.COMPLETED
    types = [e.event_type for e in sink.events]
    assert "permission_requested" in types
    assert "permission_resolved" in types
    assert "agent_completed" in types
    # 兼容：无 sink/handler 参数仍可跑
    llm2 = ScriptedLLMClient([LLMResponse(content="bye", tool_calls=())])
    agents2 = AgentService(store, llm=llm2, max_steps=3)
    r2 = agents2.run(session.session_id, "hello")
    assert r2.state.status == AgentStatus.COMPLETED


def test_tool_failed_event(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    registry = create_default_registry(workspace=ws)
    executor = ToolExecutor(registry)
    sink = RecordingEventSink()
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="read_file",
                        arguments={"path": "missing.py"},
                        arguments_raw='{"path":"missing.py"}',
                    ),
                ),
            ),
            LLMResponse(content="file missing", tool_calls=()),
        ]
    )
    state = AgentLoop(
        llm, executor, registry, max_steps=5, event_sink=sink
    ).run("read missing")
    assert state.status == AgentStatus.COMPLETED
    assert any(e.event_type == "tool_failed" for e in sink.events)
