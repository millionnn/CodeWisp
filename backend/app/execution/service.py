"""ExecutionService：在 Workspace 边界内受控执行命令（无 shell）。"""

from __future__ import annotations

import subprocess
import time
from typing import Any

from backend.app.execution.errors import InvalidExecutionRequestError
from backend.app.execution.request import ExecutionRequest
from backend.app.execution.result import ExecutionResult
from backend.app.workspace.errors import PathOutsideWorkspaceError, WorkspaceError
from backend.app.workspace.workspace import Workspace

DEFAULT_MAX_OUTPUT_CHARS = 50_000


class ExecutionService:
    """语言无关的命令执行器。

    - 不使用 shell=True
    - cwd 必须经 Workspace.resolve_path
    - 强制 timeout；截断过大 stdout/stderr
    - 可预期失败一律返回 ExecutionResult，不向外抛未捕获异常
    """

    def __init__(
        self,
        workspace: Workspace,
        *,
        max_output_chars: int = DEFAULT_MAX_OUTPUT_CHARS,
    ) -> None:
        if max_output_chars < 1:
            raise InvalidExecutionRequestError("max_output_chars 必须 >= 1")
        self._workspace = workspace
        self._max_output_chars = max_output_chars

    @property
    def workspace(self) -> Workspace:
        return self._workspace

    def run(self, request: ExecutionRequest) -> ExecutionResult:
        """执行请求并返回结构化结果。"""
        started = time.perf_counter()
        try:
            request.validate()
        except InvalidExecutionRequestError as exc:
            return self._failure_result(
                request,
                error=str(exc),
                started=started,
                metadata={"error_type": "invalid_request"},
            )

        try:
            cwd_path = self._workspace.resolve_path(request.cwd)
        except PathOutsideWorkspaceError as exc:
            return self._failure_result(
                request,
                error=str(exc),
                started=started,
                metadata={"error_type": "cwd_outside_workspace"},
            )
        except WorkspaceError as exc:
            return self._failure_result(
                request,
                error=str(exc),
                started=started,
                metadata={"error_type": "cwd_resolve_error"},
            )

        if not cwd_path.exists():
            return self._failure_result(
                request,
                error=f"cwd 不存在：{request.cwd}",
                started=started,
                metadata={"error_type": "cwd_missing"},
            )
        if not cwd_path.is_dir():
            return self._failure_result(
                request,
                error=f"cwd 不是目录：{request.cwd}",
                started=started,
                metadata={"error_type": "cwd_not_directory"},
            )

        cwd_display = self._workspace.relative_to_root(cwd_path)
        argv = request.argv()
        env = dict(request.env) if request.env is not None else None

        try:
            completed = subprocess.run(  # noqa: S603 — 有意：无 shell，argv 列表
                argv,
                cwd=str(cwd_path),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=request.timeout,
                env=env,
                check=False,
            )
        except FileNotFoundError:
            return self._failure_result(
                request,
                error=f"命令不存在或无法执行：{request.command}",
                started=started,
                cwd=cwd_display,
                metadata={"error_type": "command_not_found"},
            )
        except subprocess.TimeoutExpired as exc:
            stdout, trunc_out = self._clip(_decode_captured(exc.stdout))
            stderr, trunc_err = self._clip(_decode_captured(exc.stderr))
            if not stderr:
                stderr = f"命令超时（>{request.timeout}s）。"
            return ExecutionResult(
                success=False,
                exit_code=None,
                stdout=stdout,
                stderr=stderr,
                duration_ms=self._elapsed_ms(started),
                command=request.command,
                args=list(request.args),
                cwd=cwd_display,
                timed_out=True,
                truncated=trunc_out or trunc_err,
                metadata={"error_type": "timeout", "timeout": request.timeout},
            )
        except OSError as exc:
            return self._failure_result(
                request,
                error=f"执行失败：{exc}",
                started=started,
                cwd=cwd_display,
                metadata={"error_type": "os_error"},
            )
        except Exception as exc:  # noqa: BLE001 — 边界：未知异常结构化
            return self._failure_result(
                request,
                error=f"执行异常：{exc}",
                started=started,
                cwd=cwd_display,
                metadata={"error_type": "unexpected"},
            )

        stdout, trunc_out = self._clip(completed.stdout or "")
        stderr, trunc_err = self._clip(completed.stderr or "")
        exit_code = int(completed.returncode)
        return ExecutionResult(
            success=exit_code == 0,
            exit_code=exit_code,
            stdout=stdout,
            stderr=stderr,
            duration_ms=self._elapsed_ms(started),
            command=request.command,
            args=list(request.args),
            cwd=cwd_display,
            timed_out=False,
            truncated=trunc_out or trunc_err,
            metadata={},
        )

    def _clip(self, text: str) -> tuple[str, bool]:
        limit = self._max_output_chars
        if len(text) <= limit:
            return text, False
        return text[:limit] + "\n...[truncated]...", True

    def _failure_result(
        self,
        request: ExecutionRequest,
        *,
        error: str,
        started: float,
        cwd: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> ExecutionResult:
        return ExecutionResult(
            success=False,
            exit_code=None,
            stdout="",
            stderr=error,
            duration_ms=self._elapsed_ms(started),
            command=request.command,
            args=list(request.args),
            cwd=cwd if cwd is not None else request.cwd,
            timed_out=False,
            truncated=False,
            metadata=metadata or {},
        )

    @staticmethod
    def _elapsed_ms(started: float) -> float:
        return round((time.perf_counter() - started) * 1000, 3)


def _decode_captured(raw: str | bytes | None) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        return raw.decode("utf-8", errors="replace")
    return raw
