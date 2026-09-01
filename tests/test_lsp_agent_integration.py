"""LSP agent integration — diagnostics drive self-correction (scripted LLM)."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.agent.loop import AgentLoop
from backend.app.agent.state import AgentStatus
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.lsp.adapters import FakeLanguageServerClient
from backend.app.lsp.errors import LspUnavailableError
from backend.app.lsp.manager import LanguageServerManager
from backend.app.lsp.models import (
    Diagnostic,
    DiagnosticSeverity,
    Position,
    Range,
)
from backend.app.lsp.service import LSPService
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry
from backend.app.workspace.workspace import Workspace


class ScriptedLLMClient(LLMClient):
    def __init__(self, responses: list[LLMResponse]) -> None:
        self.config = LLMConfig(api_key="fake", base_url="http://localhost", model="fake")
        self._client = None  # type: ignore[assignment]
        self._queue = list(responses)

    def chat(self, conversation: Conversation, *, tools=None) -> LLMResponse:
        if not self._queue:
            raise LLMRequestError("empty")
        return self._queue.pop(0)


def _tc(call_id: str, name: str, arguments: dict) -> ToolCall:
    return ToolCall(
        id=call_id,
        name=name,
        arguments=arguments,
        arguments_raw=json.dumps(arguments),
    )


def test_agent_edit_diagnostics_self_correction(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text(
        "def divide(a, b):\n    return a / result\n",
        encoding="utf-8",
    )
    ws = Workspace(tmp_path)

    # First diagnostics call returns error; after edit, clean
    class FlippingFake(FakeLanguageServerClient):
        def __init__(self) -> None:
            super().__init__()
            self._n = 0

        def diagnostics(self, path: str | None = None):
            self._n += 1
            if self._n == 1:
                return [
                    Diagnostic(
                        message='"result" is not defined',
                        severity=DiagnosticSeverity.ERROR,
                        path="calc.py",
                        range=Range(
                            start=Position(1, 15),
                            end=Position(1, 21),
                        ),
                    )
                ]
            return []

    fake = FlippingFake()
    manager = LanguageServerManager()
    manager.inject_client(tmp_path, fake)
    from backend.app.lsp.detector import LanguageDetection
    from backend.app.lsp.models import LspServerStatus

    manager._detections[str(tmp_path.resolve())] = LanguageDetection(  # noqa: SLF001
        language="python",
        server="FakeLSP",
        status=LspServerStatus.AVAILABLE,
        message="test",
        command="fake",
    )
    service = LSPService(ws, manager=manager)
    registry = create_default_registry(workspace=ws, lsp_service=service)

    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(_tc("1", "lsp_diagnostics", {"path": "calc.py"}),),
            ),
            LLMResponse(
                content=None,
                tool_calls=(
                    _tc(
                        "2",
                        "edit_file",
                        {
                            "path": "calc.py",
                            "old_text": "return a / result",
                            "new_text": "return a / b",
                        },
                    ),
                ),
            ),
            LLMResponse(
                content=None,
                tool_calls=(_tc("3", "lsp_diagnostics", {"path": "calc.py"}),),
            ),
            LLMResponse(content="Fixed undefined name via diagnostics.", tool_calls=()),
        ]
    )
    loop = AgentLoop(llm, ToolExecutor(registry), registry, max_steps=10)
    state = loop.run("fix calculator with LSP", conversation=Conversation())
    assert state.status is AgentStatus.COMPLETED
    tools = [
        e.tool_name
        for e in state.events
        if e.event_type in {"tool_completed", "tool_failed"} and e.tool_name
    ]
    assert tools.count("lsp_diagnostics") >= 2
    assert "edit_file" in tools
    text = (tmp_path / "calc.py").read_text(encoding="utf-8")
    assert "return a / b" in text


def test_agent_continues_when_lsp_unavailable(tmp_path: Path) -> None:
    (tmp_path / "calc.py").write_text("def add(a,b): return a+b\n", encoding="utf-8")
    ws = Workspace(tmp_path)
    fake = FakeLanguageServerClient(fail_with=LspUnavailableError("no pyright"))
    manager = LanguageServerManager()
    manager.inject_client(tmp_path, fake)
    from backend.app.lsp.detector import LanguageDetection
    from backend.app.lsp.models import LspServerStatus

    manager._detections[str(tmp_path.resolve())] = LanguageDetection(  # noqa: SLF001
        language="python",
        server="FakeLSP",
        status=LspServerStatus.AVAILABLE,
        message="test",
        command="fake",
    )
    service = LSPService(ws, manager=manager)
    registry = create_default_registry(workspace=ws, lsp_service=service)
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(_tc("1", "lsp_diagnostics", {"path": "calc.py"}),),
            ),
            LLMResponse(
                content=None,
                tool_calls=(_tc("2", "read_file", {"path": "calc.py"}),),
            ),
            LLMResponse(content="Continued without LSP.", tool_calls=()),
        ]
    )
    loop = AgentLoop(llm, ToolExecutor(registry), registry, max_steps=8)
    state = loop.run("inspect", conversation=Conversation())
    assert state.status is AgentStatus.COMPLETED
    assert "read_file" in [
        e.tool_name for e in state.events if e.event_type == "tool_completed"
    ]
