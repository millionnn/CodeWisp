"""CLI 输入处理测试（经 AgentService，无真实网络）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.cli.interface import EXIT_COMMANDS, run_cli
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.persistence.store import SqliteStore
from backend.app.services.agent_service import AgentService


class ScriptedLLMClient(LLMClient):
    """按队列返回预设 LLMResponse。"""

    def __init__(self, responses: list[LLMResponse]) -> None:
        self.config = LLMConfig(api_key="fake", base_url="http://localhost", model="fake")
        self._client = None  # type: ignore[assignment]
        self._responses = list(responses)
        self.calls: list[dict[str, Any]] = []

    def chat(
        self,
        conversation: Conversation,
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> LLMResponse:
        self.calls.append(
            {"messages": conversation.to_api_messages(), "tools": tools}
        )
        if not self._responses:
            raise LLMRequestError("脚本响应已用尽")
        return self._responses.pop(0)


def _make_agents(
    tmp_path: Path,
    responses: list[LLMResponse],
    *,
    max_steps: int = 10,
) -> tuple[AgentService, Path]:
    ws = tmp_path / "ws"
    ws.mkdir(exist_ok=True)
    store = SqliteStore(tmp_path / "cli.db")
    store.connect()
    agents = AgentService(
        store,
        llm=ScriptedLLMClient(responses),
        max_steps=max_steps,
    )
    return agents, ws


def test_cli_multi_turn_and_history(tmp_path: Path) -> None:
    agents, ws = _make_agents(
        tmp_path,
        [
            LLMResponse(content="echo:hello", finish_reason="stop"),
            LLMResponse(content="echo:trees", finish_reason="stop"),
        ],
    )
    inputs = iter(["hello", "what about trees?", "/exit"])
    outputs: list[str] = []

    code = run_cli(
        agents,
        workspace_root=ws,
        input_fn=lambda _prompt: next(inputs),
        output_fn=outputs.append,
        show_tool_trace=False,
    )

    assert code == 0
    assert any("CodeWisp:" in line for line in outputs)
    assert any("echo:hello" in line for line in outputs)
    assert any("echo:trees" in line for line in outputs)
    # 第二轮应带上历史
    assert len(agents._llm.calls) == 2  # type: ignore[union-attr]
    assert any(
        m.get("content") == "hello"
        for m in agents._llm.calls[1]["messages"]  # type: ignore[union-attr]
    )


def test_cli_empty_input_ignored(tmp_path: Path) -> None:
    agents, ws = _make_agents(tmp_path, [])
    inputs = iter(["", "  ", "/quit"])
    outputs: list[str] = []

    code = run_cli(
        agents,
        workspace_root=ws,
        input_fn=lambda _prompt: next(inputs),
        output_fn=outputs.append,
    )

    assert code == 0
    assert any("空输入" in line for line in outputs)
    # 从未对话就退出 → 空 Session 被丢弃
    assert agents.sessions.list_sessions() == []
    assert any("已丢弃未使用的空 Session" in line for line in outputs)


def test_cli_eof_exits_cleanly(tmp_path: Path) -> None:
    agents, ws = _make_agents(tmp_path, [])
    outputs: list[str] = []

    code = run_cli(
        agents,
        workspace_root=ws,
        input_fn=lambda _prompt: None,
        output_fn=outputs.append,
    )

    assert code == 0
    assert any("再见" in line for line in outputs)
    assert agents.sessions.list_sessions() == []


def test_cli_switch_away_discards_unused_startup_session(tmp_path: Path) -> None:
    """启动新建空 Session 后 /use 旧会话，空壳应被丢弃。"""
    agents, ws = _make_agents(
        tmp_path,
        [LLMResponse(content="from-old", finish_reason="stop")],
    )
    old = agents.sessions.create_session(title="old", workspace=ws)
    agents.run(old.session_id, "prior")

    outputs: list[str] = []
    inputs = iter(["/sessions", f"/use {old.session_id}", "/sessions", "/exit"])

    code = run_cli(
        agents,
        workspace_root=ws,
        session_title="ephemeral",
        input_fn=lambda _p: next(inputs),
        output_fn=outputs.append,
        show_tool_trace=False,
    )
    assert code == 0
    assert any("已丢弃未使用的空 Session" in line for line in outputs)
    remaining = agents.sessions.list_sessions()
    assert len(remaining) == 1
    assert remaining[0].session_id == old.session_id
    assert remaining[0].title == "old"


def test_cli_shows_tool_trace_and_answer(tmp_path: Path) -> None:
    agents, ws = _make_agents(
        tmp_path,
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="c1",
                        name="calculator",
                        arguments={"expression": "2+2"},
                        arguments_raw='{"expression":"2+2"}',
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="答案是 4", finish_reason="stop"),
        ],
    )
    inputs = iter(["算 2+2", "/exit"])
    outputs: list[str] = []

    code = run_cli(
        agents,
        workspace_root=ws,
        input_fn=lambda _prompt: next(inputs),
        output_fn=outputs.append,
        show_tool_trace=True,
    )

    assert code == 0
    assert any("[工具]" in line and "calculator" in line for line in outputs)
    assert any("答案是 4" in line for line in outputs)


def test_cli_session_commands_new_use_list_history(tmp_path: Path) -> None:
    agents, ws = _make_agents(
        tmp_path,
        [
            LLMResponse(content="from-a", finish_reason="stop"),
            LLMResponse(content="from-b", finish_reason="stop"),
        ],
    )
    outputs: list[str] = []
    step = {"n": 0}
    sid_holder: dict[str, str] = {}

    def input_fn(_prompt: str) -> str | None:
        n = step["n"]
        step["n"] += 1
        if n == 0:
            return "task-a"
        if n == 1:
            for line in outputs:
                if "Session" in line and "ses_" in line:
                    # "  Session   : ses_xxx (title)"
                    for token in line.split():
                        if token.startswith("ses_"):
                            sid_holder["a"] = token
                            break
                    break
            return "/new other"
        if n == 2:
            return "task-b"
        if n == 3:
            return "/sessions"
        if n == 4:
            return f"/use {sid_holder['a']}"
        if n == 5:
            return "/history"
        if n == 6:
            return "/session"
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
    assert any("已创建 Session" in line for line in outputs)
    assert any("已切换到 Session" in line for line in outputs)
    assert any("对话" in line and "底层轨迹" in line for line in outputs)
    assert any("session_id:" in line for line in outputs)
    assert EXIT_COMMANDS


def test_cli_delete_session(tmp_path: Path) -> None:
    agents, ws = _make_agents(
        tmp_path,
        [
            LLMResponse(content="keep-me", finish_reason="stop"),
        ],
    )
    doomed = agents.sessions.create_session(title="doomed", workspace=ws)
    agents.run(doomed.session_id, "old chat")

    outputs: list[str] = []
    inputs = iter(
        [
            "hello",
            f"/delete {doomed.session_id}",
            "/sessions",
            "/exit",
        ]
    )
    code = run_cli(
        agents,
        workspace_root=ws,
        session_title="keep",
        input_fn=lambda _p: next(inputs),
        output_fn=outputs.append,
        show_tool_trace=False,
    )
    assert code == 0
    assert any(f"已删除 Session: {doomed.session_id}" in line for line in outputs)
    ids = {s.session_id for s in agents.sessions.list_sessions()}
    assert doomed.session_id not in ids
    assert len(ids) == 1


def test_cli_delete_current_session_creates_replacement(tmp_path: Path) -> None:
    agents, ws = _make_agents(
        tmp_path,
        [LLMResponse(content="reply", finish_reason="stop")],
    )
    outputs: list[str] = []
    sid_holder: dict[str, str] = {}

    def input_fn(_prompt: str) -> str | None:
        if "sid" not in sid_holder:
            for line in outputs:
                if "Session" in line and "ses_" in line:
                    for token in line.split():
                        if token.startswith("ses_"):
                            sid_holder["sid"] = token
                            break
                    if "sid" in sid_holder:
                        break
            return "hello"
        if "deleted" not in sid_holder:
            sid_holder["deleted"] = "1"
            return f"/rm {sid_holder['sid']}"
        return "/exit"

    code = run_cli(
        agents,
        workspace_root=ws,
        session_title="current",
        input_fn=input_fn,
        output_fn=outputs.append,
        show_tool_trace=False,
    )
    assert code == 0
    assert any("已删除 Session:" in line for line in outputs)
    assert any("已切换到新 Session:" in line for line in outputs)
    # 对话过的旧 Session 已删；退出时若替代 Session 未再对话也会被丢弃
    remaining = agents.sessions.list_sessions()
    assert all(s.session_id != sid_holder["sid"] for s in remaining)


def test_cli_resume_existing_session(tmp_path: Path) -> None:
    agents, ws = _make_agents(
        tmp_path,
        [
            LLMResponse(content="first", finish_reason="stop"),
            LLMResponse(content="second", finish_reason="stop"),
        ],
    )
    session = agents.sessions.create_session(title="resume-me", workspace=ws)
    agents.run(session.session_id, "hello")

    outputs: list[str] = []
    inputs = iter(["/history", "continue please", "/exit"])
    code = run_cli(
        agents,
        workspace_root=ws,
        session_id=session.session_id,
        input_fn=lambda _p: next(inputs),
        output_fn=outputs.append,
        show_tool_trace=False,
    )
    assert code == 0
    assert any("Session:" in line or "Session   :" in line for line in outputs)
    assert any("second" in line for line in outputs)
    # continue saw prior user message
    assert any(
        m.get("content") == "hello"
        for m in agents._llm.calls[-1]["messages"]  # type: ignore[union-attr]
    )
