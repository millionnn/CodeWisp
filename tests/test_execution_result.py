"""ExecutionResult 单元测试。"""

from __future__ import annotations

from backend.app.execution.result import ExecutionResult


def test_to_dict_fields() -> None:
    result = ExecutionResult(
        success=True,
        exit_code=0,
        stdout="ok\n",
        stderr="",
        duration_ms=12.5,
        command="pytest",
        args=["tests"],
        cwd=".",
        timed_out=False,
        truncated=False,
        metadata={"k": 1},
    )
    data = result.to_dict()
    assert data["success"] is True
    assert data["exit_code"] == 0
    assert data["stdout"] == "ok\n"
    assert data["command"] == "pytest"
    assert data["args"] == ["tests"]
    assert data["timed_out"] is False
    assert data["truncated"] is False
    assert data["metadata"] == {"k": 1}


def test_failure_shape() -> None:
    result = ExecutionResult(
        success=False,
        exit_code=1,
        stdout="",
        stderr="boom",
        duration_ms=1.0,
        command="python",
        timed_out=False,
    )
    assert result.to_dict()["stderr"] == "boom"
