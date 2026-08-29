"""run_command Tool 测试。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from backend.app.execution.policy import CommandPolicy
from backend.app.execution.request import ExecutionRequest
from backend.app.execution.result import ExecutionResult
from backend.app.execution.service import ExecutionService
from backend.app.tools.builtin.execution import RunCommandTool
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry
from backend.app.workspace.workspace import Workspace


class SpyExecutionService(ExecutionService):
    def __init__(self, workspace: Workspace) -> None:
        super().__init__(workspace)
        self.calls: list[ExecutionRequest] = []

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        self.calls.append(request)
        return super().run(request)


@pytest.fixture
def workspace(tmp_path: Path) -> Workspace:
    return Workspace(tmp_path)


def test_run_command_allow_executes(workspace: Workspace) -> None:
    spy = SpyExecutionService(workspace)
    tool = RunCommandTool(spy, CommandPolicy())
    result = tool.execute(
        {
            "command": sys.executable,
            "args": ["-c", "print('ok')"],
            "timeout": 10,
        }
    )
    assert result.success is True
    assert result.output["stdout"].strip() == "ok"
    assert result.metadata["policy_action"] == "allow"
    assert len(spy.calls) == 1


def test_run_command_ask_does_not_execute(workspace: Workspace) -> None:
    spy = SpyExecutionService(workspace)
    tool = RunCommandTool(spy, CommandPolicy())
    result = tool.execute({"command": "npm", "args": ["install"]})
    assert result.success is False
    assert result.output["permission_required"] is True
    assert result.metadata.get("permission_required") is True
    assert result.metadata["policy_action"] == "ask"
    assert spy.calls == []


def test_run_command_deny_does_not_execute(workspace: Workspace) -> None:
    spy = SpyExecutionService(workspace)
    tool = RunCommandTool(spy, CommandPolicy())
    result = tool.execute({"command": "sudo", "args": ["ls"]})
    assert result.success is False
    assert result.output["denied"] is True
    assert result.metadata["policy_action"] == "deny"
    assert spy.calls == []


def test_run_command_cwd_boundary(workspace: Workspace) -> None:
    tool = RunCommandTool(ExecutionService(workspace), CommandPolicy())
    result = tool.execute(
        {
            "command": sys.executable,
            "args": ["-c", "print(1)"],
            "cwd": "../",
        }
    )
    assert result.success is False
    assert "workspace" in (result.error or "").lower() or "边界" in (result.error or "")


def test_run_command_via_registry(workspace: Workspace) -> None:
    spy = SpyExecutionService(workspace)
    executor = ToolExecutor(
        create_default_registry(workspace=workspace, execution_service=spy)
    )
    result = executor.execute(
        "run_command",
        {"command": sys.executable, "args": ["-c", "print(42)"], "timeout": 10},
    )
    assert result.success is True
    assert "42" in result.output["stdout"]


def test_registry_lists_run_command(workspace: Workspace) -> None:
    names = {t.name for t in create_default_registry(workspace=workspace).list_tools()}
    assert "run_command" in names


def test_language_agnostic_mvn_request_shape(workspace: Workspace) -> None:
    """mvn 在策略上 ALLOW，本机无 Maven 时结构化失败，不崩。"""
    spy = SpyExecutionService(workspace)
    tool = RunCommandTool(spy, CommandPolicy())
    result = tool.execute({"command": "mvn", "args": ["test"], "timeout": 5})
    assert len(spy.calls) == 1
    assert spy.calls[0].command == "mvn"
    assert spy.calls[0].args == ("test",)
    # 若未安装则失败；若安装则可能 success/fail 取决于项目——tmp 空仓通常失败
    assert result.output is not None
