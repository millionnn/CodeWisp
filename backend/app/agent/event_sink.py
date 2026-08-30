"""AgentEventSink：运行时事件投递抽象（CLI / 未来 SSE）。"""

from __future__ import annotations

from typing import Protocol

from backend.app.agent.events import AgentEvent


class AgentEventSink(Protocol):
    def emit(self, event: AgentEvent) -> None:
        """消费单条 AgentEvent（应尽快返回，勿阻塞 AgentLoop 过久）。"""


class NullEventSink:
    """无操作 sink（默认）。"""

    def emit(self, event: AgentEvent) -> None:
        return None


class RecordingEventSink:
    """测试用：记录全部事件。"""

    def __init__(self) -> None:
        self.events: list[AgentEvent] = []

    def emit(self, event: AgentEvent) -> None:
        self.events.append(event)


class CompositeEventSink:
    """扇出到多个 sink。"""

    def __init__(self, *sinks: AgentEventSink) -> None:
        self._sinks = sinks

    def emit(self, event: AgentEvent) -> None:
        for sink in self._sinks:
            sink.emit(event)
