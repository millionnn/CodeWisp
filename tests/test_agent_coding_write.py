"""V0.4-B：AgentLoop + edit_file / write_file 集成测试（脚本化 LLM）。"""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend.app.agent.loop import AgentLoop
from backend.app.agent.state import AgentStatus
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


def test_agent_edit_calculator_with_verify(tmp_path: Path) -> None:
    """用户：把 calculator.py 中的已知表达式改成新表达式。

    Fake LLM：read_file → edit_file → read_file → final answer
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calculator.py").write_text(
        "def add(a, b):\n    return a + b\n",
        encoding="utf-8",
    )

    workspace = Workspace(tmp_path)
    registry = create_default_registry(workspace=workspace)
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="1",
                        name="read_file",
                        arguments={"path": "src/calculator.py"},
                        arguments_raw='{"path":"src/calculator.py"}',
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="2",
                        name="edit_file",
                        arguments={
                            "path": "src/calculator.py",
                            "old_text": "return a + b",
                            "new_text": "return a * b",
                            "expected_replacements": 1,
                        },
                        arguments_raw=(
                            '{"path":"src/calculator.py",'
                            '"old_text":"return a + b",'
                            '"new_text":"return a * b",'
                            '"expected_replacements":1}'
                        ),
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="3",
                        name="read_file",
                        arguments={"path": "src/calculator.py"},
                        arguments_raw='{"path":"src/calculator.py"}',
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content="已将 return a + b 修改为 return a * b，并完成验证。",
                finish_reason="stop",
            ),
        ]
    )
    agent = AgentLoop(llm, ToolExecutor(registry), registry)

    state = agent.run("把 calculator.py 中的 return a + b 改成 return a * b。")

    assert state.status == AgentStatus.COMPLETED
    assert state.final_answer and "a * b" in state.final_answer

    tool_names = [e.tool_name for e in state.events if e.event_type == "tool_completed"]
    assert tool_names == ["read_file", "edit_file", "read_file"]

    disk = (tmp_path / "src" / "calculator.py").read_text(encoding="utf-8")
    assert "return a * b" in disk
    assert "return a + b" not in disk

    # 最后一轮 LLM 应看到验证读回的内容
    last_tool_msgs = [m for m in llm.calls[3]["messages"] if m["role"] == "tool"]
    assert any("a * b" in m["content"] for m in last_tool_msgs)

    schema_names = {
        t["function"]["name"] for t in (llm.calls[0]["tools"] or []) if "function" in t
    }
    assert "edit_file" in schema_names and "write_file" in schema_names


def test_agent_write_file_then_read(tmp_path: Path) -> None:
    """用户：创建 utils.py。Fake LLM：write_file → read_file → final。"""
    workspace = Workspace(tmp_path)
    registry = create_default_registry(workspace=workspace)
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="1",
                        name="write_file",
                        arguments={
                            "path": "utils.py",
                            "content": "def helper():\n    return 42\n",
                        },
                        arguments_raw=(
                            '{"path":"utils.py","content":"def helper():\\n    return 42\\n"}'
                        ),
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content=None,
                tool_calls=(
                    ToolCall(
                        id="2",
                        name="read_file",
                        arguments={"path": "utils.py"},
                        arguments_raw='{"path":"utils.py"}',
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content="已创建 utils.py，helper 返回 42。",
                finish_reason="stop",
            ),
        ]
    )
    agent = AgentLoop(llm, ToolExecutor(registry), registry)
    state = agent.run("创建 utils.py")

    assert state.status == AgentStatus.COMPLETED
    assert (tmp_path / "utils.py").read_text(encoding="utf-8") == (
        "def helper():\n    return 42\n"
    )
    tool_names = [e.tool_name for e in state.events if e.event_type == "tool_completed"]
    assert tool_names == ["write_file", "read_file"]
