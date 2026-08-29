"""ExecutionService 测试（tmp_path Workspace，无网络）。"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from backend.app.execution.request import ExecutionRequest
from backend.app.execution.service import ExecutionService
from backend.app.workspace.workspace import Workspace


@pytest.fixture
def ws(tmp_path: Path) -> Workspace:
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "hello.txt").write_text("hi\n", encoding="utf-8")
    return Workspace(tmp_path)


@pytest.fixture
def service(ws: Workspace) -> ExecutionService:
    return ExecutionService(ws, max_output_chars=200)


def test_success_stdout(service: ExecutionService) -> None:
    result = service.run(
        ExecutionRequest(
            command=sys.executable,
            args=["-c", "print('hello')"],
            timeout=10,
        )
    )
    assert result.success is True
    assert result.exit_code == 0
    assert "hello" in result.stdout
    assert result.timed_out is False
    assert result.cwd == "."
    assert result.duration_ms >= 0


def test_nonzero_exit(service: ExecutionService) -> None:
    result = service.run(
        ExecutionRequest(
            command=sys.executable,
            args=["-c", "raise SystemExit(1)"],
            timeout=10,
        )
    )
    assert result.success is False
    assert result.exit_code == 1


def test_stderr(service: ExecutionService) -> None:
    result = service.run(
        ExecutionRequest(
            command=sys.executable,
            args=["-c", "import sys; print('err', file=sys.stderr)"],
            timeout=10,
        )
    )
    assert result.success is True
    assert "err" in result.stderr


def test_timeout(service: ExecutionService) -> None:
    result = service.run(
        ExecutionRequest(
            command=sys.executable,
            args=["-c", "import time; time.sleep(5)"],
            timeout=0.3,
        )
    )
    assert result.success is False
    assert result.timed_out is True
    assert result.exit_code is None
    assert result.metadata.get("error_type") == "timeout"


def test_command_not_found(service: ExecutionService) -> None:
    result = service.run(
        ExecutionRequest(command="codewisp_no_such_binary_xyz", timeout=5)
    )
    assert result.success is False
    assert result.exit_code is None
    assert result.metadata.get("error_type") == "command_not_found"
    assert "不存在" in result.stderr or "无法执行" in result.stderr


def test_cwd_subdir(service: ExecutionService, ws: Workspace) -> None:
    result = service.run(
        ExecutionRequest(
            command=sys.executable,
            args=["-c", "import pathlib; print(pathlib.Path('hello.txt').read_text())"],
            cwd="src",
            timeout=10,
        )
    )
    assert result.success is True
    assert "hi" in result.stdout
    assert result.cwd == "src"


def test_cwd_outside_rejected(service: ExecutionService) -> None:
    result = service.run(
        ExecutionRequest(
            command=sys.executable,
            args=["-c", "print(1)"],
            cwd="../",
            timeout=5,
        )
    )
    assert result.success is False
    assert result.metadata.get("error_type") == "cwd_outside_workspace"


def test_cwd_absolute_outside(service: ExecutionService) -> None:
    result = service.run(
        ExecutionRequest(
            command=sys.executable,
            args=["-c", "print(1)"],
            cwd="/tmp",
            timeout=5,
        )
    )
    assert result.success is False
    assert result.metadata.get("error_type") == "cwd_outside_workspace"


def test_cwd_missing(service: ExecutionService) -> None:
    result = service.run(
        ExecutionRequest(
            command=sys.executable,
            args=["-c", "print(1)"],
            cwd="no_such_dir",
            timeout=5,
        )
    )
    assert result.success is False
    assert result.metadata.get("error_type") == "cwd_missing"


def test_output_truncation(ws: Workspace) -> None:
    svc = ExecutionService(ws, max_output_chars=40)
    result = svc.run(
        ExecutionRequest(
            command=sys.executable,
            args=["-c", "print('X' * 200)"],
            timeout=10,
        )
    )
    assert result.success is True
    assert result.truncated is True
    assert "[truncated]" in result.stdout
    assert len(result.stdout) < 200


def test_invalid_request_empty_command(service: ExecutionService) -> None:
    result = service.run(ExecutionRequest(command=""))
    assert result.success is False
    assert result.metadata.get("error_type") == "invalid_request"


def test_invalid_timeout_via_service(service: ExecutionService) -> None:
    result = service.run(ExecutionRequest(command="echo", timeout=999))
    assert result.success is False
    assert result.metadata.get("error_type") == "invalid_request"


def test_language_agnostic_argv_shape(service: ExecutionService) -> None:
    """无需安装 mvn/cargo：证明 Request→argv 与语言无关，且 not-found 结构化。"""
    for cmd, args in (("mvn", ["test"]), ("cargo", ["test"]), ("go", ["test", "./..."])):
        result = service.run(ExecutionRequest(command=cmd, args=args, timeout=5))
        assert result.command == cmd
        assert result.args == args
        # 本机可能没有这些命令；若没有则应为 command_not_found，而非崩溃
        if not result.success:
            assert result.metadata.get("error_type") in {
                "command_not_found",
                "os_error",
            }


def test_symlink_cwd_escape(service: ExecutionService, ws: Workspace, tmp_path: Path) -> None:
    outside = tmp_path.parent / "exec_outside_cwd"
    outside.mkdir(exist_ok=True)
    link = tmp_path / "escape_link"
    try:
        link.symlink_to(outside)
    except OSError:
        pytest.skip("无法创建 symlink")
    result = service.run(
        ExecutionRequest(
            command=sys.executable,
            args=["-c", "print(1)"],
            cwd="escape_link",
            timeout=5,
        )
    )
    assert result.success is False
    assert result.metadata.get("error_type") == "cwd_outside_workspace"
