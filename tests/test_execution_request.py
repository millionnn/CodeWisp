"""ExecutionRequest 单元测试。"""

from __future__ import annotations

import pytest

from backend.app.execution.errors import InvalidExecutionRequestError
from backend.app.execution.request import (
    DEFAULT_TIMEOUT_SECONDS,
    MAX_TIMEOUT_SECONDS,
    ExecutionRequest,
)


def test_defaults() -> None:
    req = ExecutionRequest(command="pytest")
    assert req.command == "pytest"
    assert req.args == ()
    assert req.cwd == "."
    assert req.timeout == DEFAULT_TIMEOUT_SECONDS
    assert req.env is None


def test_command_stripped_and_args_tuple() -> None:
    req = ExecutionRequest(command="  npm  ", args=["test", "--watch=false"])
    assert req.command == "npm"
    assert req.args == ("test", "--watch=false")
    assert req.argv() == ["npm", "test", "--watch=false"]


def test_empty_cwd_becomes_dot() -> None:
    req = ExecutionRequest(command="go", cwd="  ")
    assert req.cwd == "."


def test_env_normalized() -> None:
    req = ExecutionRequest(command="node", env={"FOO": "1"})
    assert dict(req.env) == {"FOO": "1"}


def test_validate_ok() -> None:
    ExecutionRequest(command="cargo", args=["test"], timeout=10).validate()


def test_validate_empty_command() -> None:
    req = ExecutionRequest(command="   ")
    with pytest.raises(InvalidExecutionRequestError, match="command"):
        req.validate()


def test_validate_timeout_too_large() -> None:
    req = ExecutionRequest(command="make", timeout=MAX_TIMEOUT_SECONDS + 1)
    with pytest.raises(InvalidExecutionRequestError, match="上限"):
        req.validate()


def test_validate_timeout_too_small() -> None:
    req = ExecutionRequest(command="make", timeout=0.01)
    with pytest.raises(InvalidExecutionRequestError, match="过小"):
        req.validate()


def test_invalid_timeout_type() -> None:
    with pytest.raises(InvalidExecutionRequestError, match="timeout"):
        ExecutionRequest(command="make", timeout="fast")  # type: ignore[arg-type]


def test_to_dict_serializable() -> None:
    data = ExecutionRequest(command="mvn", args=["test"], cwd="backend").to_dict()
    assert data["command"] == "mvn"
    assert data["args"] == ["test"]
    assert data["cwd"] == "backend"
