"""V0.4-A：AgentLoop + 只读 Coding Tools 集成测试（脚本化 LLM）。"""

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


def test_agent_finds_and_reads_calculator(tmp_path: Path) -> None:
    """用户：找到 calculator.py 并读取它。

    Fake LLM：glob → read_file → final answer
    """
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "calculator.py").write_text(
        "def mul(a, b):\n    return a * b\n",
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
                        name="glob",
                        arguments={"pattern": "**/calculator.py"},
                        arguments_raw='{"pattern":"**/calculator.py"}',
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
                        arguments={"path": "src/calculator.py"},
                        arguments_raw='{"path":"src/calculator.py"}',
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content="calculator.py 定义了 mul(a, b)。",
                finish_reason="stop",
            ),
        ]
    )
    agent = AgentLoop(llm, ToolExecutor(registry), registry)

    state = agent.run("找到 calculator.py 并读取它。")

    assert state.status == AgentStatus.COMPLETED
    assert state.final_answer and "mul" in state.final_answer
    assert state.step == 3

    tool_names = [e.tool_name for e in state.events if e.event_type == "tool_completed"]
    assert tool_names == ["glob", "read_file"]

    # 第二次 LLM 调用应看到 glob observation；第三次看到文件内容
    third_msgs = llm.calls[2]["messages"]
    tool_msgs = [m for m in third_msgs if m["role"] == "tool"]
    assert any("mul" in m["content"] for m in tool_msgs)

    # schema 中包含 coding tools
    schema_names = {
        t["function"]["name"] for t in (llm.calls[0]["tools"] or []) if "function" in t
    }
    assert "glob" in schema_names and "read_file" in schema_names
