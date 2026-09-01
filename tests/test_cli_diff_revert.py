"""V0.9 Phase 4：CLI /diff /revert UX。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.agent.state import AgentStatus
from backend.app.changes.models import ChangeType
from backend.app.cli.interface import (
    _human_run_label,
    _human_step_label,
    run_cli,
)
from backend.app.cli.render_diff import render_file_diffs
from backend.app.cli.theme import reset_theme_cache
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import LLMRequestError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.persistence.store import SqliteStore
from backend.app.permissions.decision import PermissionDecision
from backend.app.services.agent_service import AgentService
from backend.app.session.service import SessionService


class ScriptedLLMClient(LLMClient):
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
            raise LLMRequestError("无更多脚本响应")
        return self._queue.pop(0)


def test_render_file_diffs_plain(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    reset_theme_cache()
    from backend.app.changes.models import FileDiff
    from backend.app.cli.render_diff import format_numbered_diff

    lines: list[str] = []
    diffs = [
        FileDiff(
            path="calc.py",
            change_type=ChangeType.MODIFIED,
            before="line1\nreturn a - b\nline3\n",
            after="line1\nreturn a + b\nline3\n",
        )
    ]
    render_file_diffs(diffs, title="Diff · test", output_fn=lines.append)
    blob = "\n".join(lines)
    assert "calc.py" in blob
    assert "return a + b" in blob
    numbered = format_numbered_diff(diffs[0])
    assert "2" in numbered  # line number for changed line
    assert "-" in numbered and "+" in numbered
    reset_theme_cache()


def test_cli_diff_and_revert_flow(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    reset_theme_cache()
    ws = tmp_path / "proj"
    ws.mkdir()
    (ws / "calc.py").write_text("return a - b\n", encoding="utf-8")
    store = SqliteStore(tmp_path / "cw.db")
    store.connect()
    session = SessionService(store).create_session(title="cli-diff", workspace=ws)

    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="tc_e",
                        name="edit_file",
                        arguments={
                            "path": "calc.py",
                            "old_text": "return a - b",
                            "new_text": "return a + b",
                        },
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="fixed", tool_calls=(), finish_reason="stop"),
        ]
    )
    agents = AgentService(store, llm=llm, max_steps=5)
    # 先跑一轮产生 change
    result = agents.run(session.session_id, "fix add")
    assert result.state.status == AgentStatus.COMPLETED
    run_id = result.run.agent_run_id
    step_id = agents.list_run_file_changes(run_id)[0].agent_step_id

    outputs: list[str] = []
    # /diff → latest；/diff step；/revert step + y；/exit
    answers = iter(
        [
            "/diff",
            f"/diff step {step_id}",
            f"/diff run {run_id}",
            f"/revert step {step_id}",
            "",  # default: Revert entire · N file(s)
            "y",  # permission allow
            "/exit",
        ]
    )

    code = run_cli(
        agents,
        workspace_root=ws,
        session_id=session.session_id,
        input_fn=lambda _p: next(answers),
        output_fn=outputs.append,
        show_tool_trace=False,
    )
    assert code == 0
    blob = "\n".join(outputs)
    assert "calc.py" in blob
    assert "return a + b" in blob or "+return a + b" in blob
    assert "Revert 完成" in blob or "已恢复" in blob
    assert (ws / "calc.py").read_text(encoding="utf-8") == "return a - b\n"
    # 可读标签：用户任务 + 文件 +/-
    step_label = _human_step_label(agents, step_id, result.run)
    assert "Step #" in step_label
    assert "calc.py" in step_label
    assert "+" in step_label and "-" in step_label
    assert step_id not in step_label
    run_label = _human_run_label(agents, result.run)
    assert "Run #" in run_label
    assert "calc.py" in run_label or "fix add" in run_label
    assert "+" in run_label or "fix add" in run_label
    reset_theme_cache()


def test_cli_help_lists_diff_revert(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.setenv("NO_COLOR", "1")
    reset_theme_cache()
    ws = tmp_path / "proj"
    ws.mkdir()
    store = SqliteStore(tmp_path / "cw.db")
    store.connect()
    agents = AgentService(
        store,
        llm=ScriptedLLMClient([]),
        max_steps=3,
    )
    SessionService(store).create_session(title="h", workspace=ws)
    outputs: list[str] = []
    answers = iter(["/help", "/exit"])
    # need a session - run_cli creates one
    code = run_cli(
        agents,
        workspace_root=ws,
        input_fn=lambda _p: next(answers),
        output_fn=outputs.append,
        show_tool_trace=False,
    )
    assert code == 0
    blob = "\n".join(outputs)
    assert "/diff" in blob and "/revert" in blob
    reset_theme_cache()
