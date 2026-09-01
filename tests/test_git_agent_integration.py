"""Git agent integration tests."""

from __future__ import annotations

import json
from pathlib import Path

from backend.app.agent.loop import AgentLoop
from backend.app.agent.state import AgentStatus
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.handler import ScriptedPermissionHandler
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry
from backend.app.workspace.workspace import Workspace
from tests.git_helpers import git_commit_all, init_git_repo


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


def test_agent_git_workflow(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    (tmp_path / "app" / "calculator.py").parent.mkdir(parents=True)
    (tmp_path / "app" / "__init__.py").write_text("", encoding="utf-8")
    (tmp_path / "app" / "calculator.py").write_text(
        "def add(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    git_commit_all(tmp_path, "add calculator")

    ws = Workspace(tmp_path)
    registry = create_default_registry(workspace=ws)
    llm = ScriptedLLMClient(
        [
            LLMResponse(content=None, tool_calls=(_tc("1", "git_status", {}),)),
            LLMResponse(content=None, tool_calls=(_tc("2", "read_file", {"path": "app/calculator.py"}),)),
            LLMResponse(
                content=None,
                tool_calls=(
                    _tc(
                        "3",
                        "edit_file",
                        {
                            "path": "app/calculator.py",
                            "old_text": "return a - b",
                            "new_text": "return a + b",
                        },
                    ),
                ),
            ),
            LLMResponse(content=None, tool_calls=(_tc("4", "git_diff", {}),)),
            LLMResponse(content="Fixed calculator bug.", tool_calls=()),
        ]
    )
    loop = AgentLoop(llm, ToolExecutor(registry), registry, max_steps=10)
    state = loop.run("fix calculator", conversation=Conversation())
    assert state.status is AgentStatus.COMPLETED
    tools = [
        e.tool_name
        for e in state.events
        if e.event_type in {"tool_completed", "tool_failed"} and e.tool_name
    ]
    assert "git_status" in tools
    assert "git_diff" in tools


def test_agent_commit_with_permission(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    (tmp_path / "calc.py").write_text("x=1\n", encoding="utf-8")

    ws = Workspace(tmp_path)
    handler = ScriptedPermissionHandler([PermissionDecision.ALLOW])
    registry = create_default_registry(workspace=ws, permission_handler=handler)
    llm = ScriptedLLMClient(
        [
            LLMResponse(content=None, tool_calls=(_tc("1", "git_status", {}),)),
            LLMResponse(content=None, tool_calls=(_tc("2", "git_diff", {}),)),
            LLMResponse(
                content=None,
                tool_calls=(_tc("3", "git_commit", {"message": "feat: fix"}),),
            ),
            LLMResponse(content="Committed.", tool_calls=()),
        ]
    )
    loop = AgentLoop(llm, ToolExecutor(registry), registry, max_steps=10)
    state = loop.run("commit these changes", conversation=Conversation())
    assert state.status is AgentStatus.COMPLETED
    assert len(handler.requests) >= 1


def test_agent_commit_denied(tmp_path: Path) -> None:
    init_git_repo(tmp_path)
    (tmp_path / "calc.py").write_text("x=1\n", encoding="utf-8")

    ws = Workspace(tmp_path)
    handler = ScriptedPermissionHandler([PermissionDecision.DENY])
    registry = create_default_registry(workspace=ws, permission_handler=handler)
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(_tc("1", "git_commit", {"message": "feat: fix"}),),
            ),
            LLMResponse(content="User denied commit.", tool_calls=()),
        ]
    )
    loop = AgentLoop(llm, ToolExecutor(registry), registry, max_steps=5)
    state = loop.run("commit", conversation=Conversation())
    # Agent should continue after DENY
    assert state.status is AgentStatus.COMPLETED
