"""V0.5：Self-Correction 集成测试（脚本化 LLM，确定性 tmp 仓库）。

框架不规定修复顺序；下列脚本路径仅为验收场景，证明
Observation → 再决策 → 有限迭代 的闭环可行。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from typing import Any

from backend.app.agent.loop import AgentLoop
from backend.app.agent.state import AgentStatus
from backend.app.execution.policy import CommandPolicy
from backend.app.execution.request import ExecutionRequest
from backend.app.execution.result import ExecutionResult
from backend.app.execution.service import ExecutionService
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


class SpyExecutionService(ExecutionService):
    def __init__(self, workspace: Workspace) -> None:
        super().__init__(workspace)
        self.calls: list[ExecutionRequest] = []

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        self.calls.append(request)
        return super().run(request)


def _tc(call_id: str, name: str, arguments: dict[str, Any]) -> ToolCall:
    return ToolCall(
        id=call_id,
        name=name,
        arguments=arguments,
        arguments_raw=json.dumps(arguments),
    )


def _pytest_args() -> list[str]:
    return ["-m", "pytest", "-q"]


def _write_mini_project(
    root: Path,
    *,
    calculator_body: str,
    helper_body: str | None = None,
) -> None:
    """小型可测工程：app.calculator + tests（pyproject 配置 pythonpath）。"""
    (root / "app").mkdir()
    (root / "app" / "__init__.py").write_text("", encoding="utf-8")
    (root / "app" / "calculator.py").write_text(calculator_body, encoding="utf-8")
    if helper_body is not None:
        (root / "app" / "helper.py").write_text(helper_body, encoding="utf-8")
    (root / "tests").mkdir()
    (root / "tests" / "test_calculator.py").write_text(
        "from app.calculator import add\n\n\ndef test_add():\n    assert add(2, 2) == 4\n",
        encoding="utf-8",
    )
    (root / "pyproject.toml").write_text(
        "[tool.pytest.ini_options]\n"
        'testpaths = ["tests"]\n'
        'pythonpath = ["."]\n',
        encoding="utf-8",
    )


def _tool_names(state) -> list[str]:
    return [
        e.tool_name
        for e in state.events
        if e.event_type in {"tool_completed", "tool_failed"} and e.tool_name
    ]


def test_simple_repair_pytest_edit_pytest(tmp_path: Path) -> None:
    """Test A：实现错误 → pytest 失败 → edit → pytest 通过 → final。"""
    _write_mini_project(
        tmp_path,
        calculator_body=(
            "def add(a, b):\n"
            "    return a - b  # BUG\n"
        ),
    )
    workspace = Workspace(tmp_path)
    spy = SpyExecutionService(workspace)
    registry = create_default_registry(workspace=workspace, execution_service=spy)
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    _tc(
                        "1",
                        "run_command",
                        {
                            "command": sys.executable,
                            "args": _pytest_args(),
                            "timeout": 30,
                        },
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content=None,
                tool_calls=(
                    _tc("2", "read_file", {"path": "app/calculator.py"}),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content=None,
                tool_calls=(
                    _tc(
                        "3",
                        "edit_file",
                        {
                            "path": "app/calculator.py",
                            "old_text": "return a - b  # BUG",
                            "new_text": "return a + b",
                            "expected_replacements": 1,
                        },
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content=None,
                tool_calls=(
                    _tc(
                        "4",
                        "run_command",
                        {
                            "command": sys.executable,
                            "args": _pytest_args(),
                            "timeout": 30,
                        },
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content="已修复 add：2+2=4，测试通过。",
                finish_reason="stop",
            ),
        ]
    )
    agent = AgentLoop(llm, ToolExecutor(registry), registry, max_steps=10)
    state = agent.run("修复这个项目的测试失败。")

    assert state.status == AgentStatus.COMPLETED
    assert state.termination_reason == "completed"
    assert "通过" in (state.final_answer or "")
    assert _tool_names(state) == [
        "run_command",
        "read_file",
        "edit_file",
        "run_command",
    ]
    assert "return a + b" in (tmp_path / "app" / "calculator.py").read_text(
        encoding="utf-8"
    )
    assert len(spy.calls) == 2
    verify = ExecutionService(workspace).run(
        ExecutionRequest(command=sys.executable, args=_pytest_args(), timeout=30)
    )
    assert verify.success is True
    assert verify.exit_code == 0


def test_repair_needs_search_code(tmp_path: Path) -> None:
    """Test B：错误藏在 helper，需 search → read → edit → 再测。"""
    _write_mini_project(
        tmp_path,
        calculator_body=(
            "from app.helper import combine\n\n\n"
            "def add(a, b):\n"
            "    return combine(a, b)\n"
        ),
        helper_body=(
            "def combine(a, b):\n"
            "    return a * b  # BUG: should add\n"
        ),
    )
    # 额外写一句独特标记便于 search
    helper = tmp_path / "app" / "helper.py"
    helper.write_text(
        "def combine(a, b):\n"
        "    return a * b  # UNIQUE_BUG_MARKER\n",
        encoding="utf-8",
    )

    workspace = Workspace(tmp_path)
    registry = create_default_registry(workspace=workspace)
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    _tc(
                        "1",
                        "run_command",
                        {
                            "command": sys.executable,
                            "args": _pytest_args(),
                            "timeout": 30,
                        },
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content=None,
                tool_calls=(
                    _tc("2", "search_code", {"query": "UNIQUE_BUG_MARKER"}),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content=None,
                tool_calls=(_tc("3", "read_file", {"path": "app/helper.py"}),),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content=None,
                tool_calls=(
                    _tc(
                        "4",
                        "edit_file",
                        {
                            "path": "app/helper.py",
                            "old_text": "return a * b  # UNIQUE_BUG_MARKER",
                            "new_text": "return a + b",
                            "expected_replacements": 1,
                        },
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content=None,
                tool_calls=(
                    _tc(
                        "5",
                        "run_command",
                        {
                            "command": sys.executable,
                            "args": _pytest_args(),
                            "timeout": 30,
                        },
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content="已通过 search_code 定位 helper 并修复，测试通过。",
                finish_reason="stop",
            ),
        ]
    )
    agent = AgentLoop(llm, ToolExecutor(registry), registry, max_steps=12)
    state = agent.run("测试失败了，请找出原因并修复。")

    assert state.status == AgentStatus.COMPLETED
    assert "search_code" in _tool_names(state)
    assert "edit_file" in _tool_names(state)
    assert "return a + b" in helper.read_text(encoding="utf-8")
    verify = ExecutionService(workspace).run(
        ExecutionRequest(command=sys.executable, args=_pytest_args(), timeout=30)
    )
    assert verify.success is True


def test_multi_step_repair_first_edit_insufficient(tmp_path: Path) -> None:
    """Test C：第一次修改未修好 → 再分析修改 → 最终通过。"""
    _write_mini_project(
        tmp_path,
        calculator_body=(
            "def add(a, b):\n"
            "    return a - b  # BUG\n"
        ),
    )
    workspace = Workspace(tmp_path)
    registry = create_default_registry(workspace=workspace)
    llm = ScriptedLLMClient(
        [
            # 1 fail
            LLMResponse(
                content=None,
                tool_calls=(
                    _tc(
                        "1",
                        "run_command",
                        {
                            "command": sys.executable,
                            "args": _pytest_args(),
                            "timeout": 30,
                        },
                    ),
                ),
                finish_reason="tool_calls",
            ),
            # 2 wrong fix (still wrong)
            LLMResponse(
                content=None,
                tool_calls=(
                    _tc(
                        "2",
                        "edit_file",
                        {
                            "path": "app/calculator.py",
                            "old_text": "return a - b  # BUG",
                            "new_text": "return a * b  # still wrong",
                            "expected_replacements": 1,
                        },
                    ),
                ),
                finish_reason="tool_calls",
            ),
            # 3 still fail
            LLMResponse(
                content=None,
                tool_calls=(
                    _tc(
                        "3",
                        "run_command",
                        {
                            "command": sys.executable,
                            "args": _pytest_args(),
                            "timeout": 30,
                        },
                    ),
                ),
                finish_reason="tool_calls",
            ),
            # 4 correct fix
            LLMResponse(
                content=None,
                tool_calls=(
                    _tc(
                        "4",
                        "edit_file",
                        {
                            "path": "app/calculator.py",
                            "old_text": "return a * b  # still wrong",
                            "new_text": "return a + b",
                            "expected_replacements": 1,
                        },
                    ),
                ),
                finish_reason="tool_calls",
            ),
            # 5 pass
            LLMResponse(
                content=None,
                tool_calls=(
                    _tc(
                        "5",
                        "run_command",
                        {
                            "command": sys.executable,
                            "args": _pytest_args(),
                            "timeout": 30,
                        },
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content="第一轮修复无效，第二轮已改正，测试通过。",
                finish_reason="stop",
            ),
        ]
    )
    agent = AgentLoop(llm, ToolExecutor(registry), registry, max_steps=12)
    state = agent.run("请修复直到测试通过。")

    assert state.status == AgentStatus.COMPLETED
    names = _tool_names(state)
    assert names.count("edit_file") == 2
    assert names.count("run_command") == 3
    assert "return a + b" in (tmp_path / "app" / "calculator.py").read_text(
        encoding="utf-8"
    )
    verify = ExecutionService(workspace).run(
        ExecutionRequest(command=sys.executable, args=_pytest_args(), timeout=30)
    )
    assert verify.success is True


def test_max_steps_stops_unfixable_loop(tmp_path: Path) -> None:
    """永远无法通过：反复 run_command，耗尽预算 → MAX_STEPS。"""
    _write_mini_project(
        tmp_path,
        calculator_body="def add(a, b):\n    return 0  # unfixable\n",
    )
    workspace = Workspace(tmp_path)
    registry = create_default_registry(workspace=workspace)
    forever = LLMResponse(
        content=None,
        tool_calls=(
            _tc(
                "x",
                "run_command",
                {
                    "command": sys.executable,
                    "args": _pytest_args(),
                    "timeout": 30,
                },
            ),
        ),
        finish_reason="tool_calls",
    )
    llm = ScriptedLLMClient([forever, forever, forever, forever])
    agent = AgentLoop(llm, ToolExecutor(registry), registry, max_steps=3)
    state = agent.run("一直修到测试通过")

    assert state.status == AgentStatus.MAX_STEPS
    assert state.termination_reason == "max_steps"
    assert state.step == 3
    assert len(llm.calls) == 3


def test_permission_required_interrupts_repair(tmp_path: Path) -> None:
    """修复过程中遇到 ASK → PERMISSION_REQUIRED，subprocess 不启动。"""
    _write_mini_project(
        tmp_path,
        calculator_body="def add(a, b):\n    return a - b\n",
    )
    workspace = Workspace(tmp_path)
    spy = SpyExecutionService(workspace)
    registry = create_default_registry(
        workspace=workspace,
        execution_service=spy,
        command_policy=CommandPolicy(),
    )
    llm = ScriptedLLMClient(
        [
            LLMResponse(
                content=None,
                tool_calls=(
                    _tc(
                        "1",
                        "run_command",
                        {
                            "command": sys.executable,
                            "args": _pytest_args(),
                            "timeout": 30,
                        },
                    ),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(
                content=None,
                tool_calls=(
                    _tc("2", "run_command", {"command": "git", "args": ["push"]}),
                ),
                finish_reason="tool_calls",
            ),
            LLMResponse(content="不应到达", finish_reason="stop"),
        ]
    )
    agent = AgentLoop(llm, ToolExecutor(registry), registry, max_steps=10)
    state = agent.run("修复测试；必要时推送")

    assert state.status == AgentStatus.PERMISSION_REQUIRED
    assert state.termination_reason == "permission_required"
    # 仅第一次 pytest 真正执行；git push 未进 Service
    assert len(spy.calls) == 1
    assert spy.calls[0].args[:2] == ("-m", "pytest") or list(spy.calls[0].args)[
        :2
    ] == ["-m", "pytest"]
    assert len(llm.calls) == 2
