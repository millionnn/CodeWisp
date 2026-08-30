"""最终回答流式（answer_delta）与 chat_stream 回退测试。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.agent.event_sink import RecordingEventSink
from backend.app.agent.loop import AgentLoop
from backend.app.agent.state import AgentStatus
from backend.app.cli.event_sink import CliEventSink
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry
from backend.app.workspace.workspace import Workspace


class ScriptedLLMClient(LLMClient):
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.config = LLMConfig(api_key="fake", base_url="http://localhost", model="fake")
        self._client = None  # type: ignore[assignment]
        self._queue = list(responses)
        self.calls: list[dict[str, Any]] = []
        self.stream_calls = 0

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

    def chat_stream(
        self,
        conversation: Conversation,
        *,
        tools: list[dict[str, Any]] | None = None,
        on_text_delta: Any = None,
        on_text_discard: Any = None,
    ) -> LLMResponse:
        self.stream_calls += 1
        return super().chat_stream(
            conversation,
            tools=tools,
            on_text_delta=on_text_delta,
            on_text_discard=on_text_discard,
        )


def test_answer_delta_streamed_for_final_text(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    registry = create_default_registry(workspace=ws)
    executor = ToolExecutor(registry)
    sink = RecordingEventSink()
    llm = ScriptedLLMClient(
        [LLMResponse(content="你好，世界。完成。", tool_calls=())]
    )
    state = AgentLoop(
        llm, executor, registry, max_steps=3, event_sink=sink
    ).run("hi")
    assert state.status == AgentStatus.COMPLETED
    assert llm.stream_calls >= 1
    deltas = [e for e in sink.events if e.event_type == "answer_delta"]
    assert deltas
    assert "".join(e.metadata["delta"] for e in deltas) == "你好，世界。完成。"
    assert any(e.event_type == "llm_started" for e in sink.events)
    # tool 轮不推送正文
    assert state.final_answer == "你好，世界。完成。"


def test_tool_round_does_not_stream_answer(tmp_path: Path) -> None:
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
                        name="calculator",
                        arguments={"expression": "1+1"},
                        arguments_raw='{"expression":"1+1"}',
                    ),
                ),
            ),
            LLMResponse(content="等于 2", tool_calls=()),
        ]
    )
    state = AgentLoop(
        llm, executor, registry, max_steps=5, event_sink=sink
    ).run("1+1")
    assert state.status == AgentStatus.COMPLETED
    # 仅最终回答有 delta；tool 轮 content 为空故无 delta
    joined = "".join(
        e.metadata["delta"] for e in sink.events if e.event_type == "answer_delta"
    )
    assert joined == "等于 2"


def test_cli_event_sink_streams_answer_once() -> None:
    outputs: list[str] = []
    sink = CliEventSink(output_fn=outputs.append, model_id="fake")
    from backend.app.agent.events import AgentEvent

    sink.emit(AgentEvent(event_type="llm_started", step=1, metadata={"model_id": "fake"}))
    sink.emit(AgentEvent(event_type="answer_delta", step=1, metadata={"delta": "Hel"}))
    sink.emit(AgentEvent(event_type="answer_delta", step=1, metadata={"delta": "lo"}))
    sink.emit(
        AgentEvent(
            event_type="agent_completed",
            step=1,
            metadata={"status": "completed"},
        )
    )
    assert sink.answer_streamed is True
    blob = "\n".join(outputs)
    assert "CodeWisp:" in blob
    assert "Hello" in blob
