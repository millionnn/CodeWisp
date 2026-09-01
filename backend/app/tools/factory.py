"""默认工具注册工厂。"""

from __future__ import annotations

from pathlib import Path

from backend.app.execution.policy import CommandPolicy
from backend.app.execution.service import ExecutionService
from backend.app.tools.builtin.calculator import CalculatorTool
from backend.app.tools.builtin.execution import RunCommandTool
from backend.app.tools.builtin.git import (
    create_git_branch_tool,
    create_git_commit_tool,
    create_git_diff_tool,
    create_git_log_tool,
    create_git_status_tool,
)
from backend.app.tools.builtin.lsp import (
    create_lsp_definition_tool,
    create_lsp_diagnostics_tool,
    create_lsp_hover_tool,
    create_lsp_references_tool,
    create_lsp_symbols_tool,
)
from backend.app.tools.builtin.time import GetCurrentTimeTool
from backend.app.tools.builtin.workspace import (
    EditFileTool,
    GlobTool,
    ListFilesTool,
    ReadFileTool,
    SearchCodeTool,
    WriteFileTool,
)
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.registry import ToolRegistry
from backend.app.workspace.workspace import Workspace


def create_default_registry(
    *,
    workspace: Workspace | None = None,
    workspace_root: str | Path | None = None,
    execution_service: ExecutionService | None = None,
    command_policy: CommandPolicy | None = None,
    permission_handler: object | None = None,
    session_id: str | None = None,
    agent_run_id: str | None = None,
    on_permission_wait: object | None = None,
    on_permission_resolved: object | None = None,
    on_command_line: object | None = None,
    lsp_service: object | None = None,
) -> ToolRegistry:
    """创建并注册内置工具（只读 / 写入 / 受控执行）。

    workspace / workspace_root 指向「目标仓库」，不是 CodeWisp 源码树。
    皆空时使用 cwd（与 resolve_workspace_root 的默认一致）。
    未来 Web Session 应传入该会话绑定的 Workspace 实例。
    """
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    registry.register(GetCurrentTimeTool())

    ws = workspace
    if ws is None:
        root = Path(workspace_root) if workspace_root is not None else Path.cwd()
        ws = Workspace(root)

    registry.register(ListFilesTool(ws))
    registry.register(GlobTool(ws))
    registry.register(ReadFileTool(ws))
    registry.register(SearchCodeTool(ws))
    registry.register(EditFileTool(ws))
    registry.register(WriteFileTool(ws))

    service = execution_service if execution_service is not None else ExecutionService(ws)
    policy = command_policy if command_policy is not None else CommandPolicy()
    registry.register(
        RunCommandTool(
            service,
            policy,
            permission_handler=permission_handler,  # type: ignore[arg-type]
            session_id=session_id,
            agent_run_id=agent_run_id,
            on_permission_wait=on_permission_wait,
            on_permission_resolved=on_permission_resolved,
            on_command_line=on_command_line,
        )
    )

    git_kwargs = {
        "permission_handler": permission_handler,
        "session_id": session_id,
        "agent_run_id": agent_run_id,
        "on_permission_wait": on_permission_wait,
        "on_permission_resolved": on_permission_resolved,
    }
    registry.register(create_git_status_tool(ws))
    registry.register(create_git_diff_tool(ws))
    registry.register(create_git_log_tool(ws))
    registry.register(create_git_branch_tool(ws, **git_kwargs))  # type: ignore[arg-type]
    registry.register(create_git_commit_tool(ws, **git_kwargs))  # type: ignore[arg-type]

    lsp_kwargs = {"service": lsp_service} if lsp_service is not None else {}
    registry.register(create_lsp_diagnostics_tool(ws, **lsp_kwargs))  # type: ignore[arg-type]
    registry.register(create_lsp_definition_tool(ws, **lsp_kwargs))  # type: ignore[arg-type]
    registry.register(create_lsp_references_tool(ws, **lsp_kwargs))  # type: ignore[arg-type]
    registry.register(create_lsp_symbols_tool(ws, **lsp_kwargs))  # type: ignore[arg-type]
    registry.register(create_lsp_hover_tool(ws, **lsp_kwargs))  # type: ignore[arg-type]

    return registry


def create_default_executor(
    *,
    workspace: Workspace | None = None,
    workspace_root: str | Path | None = None,
    execution_service: ExecutionService | None = None,
    command_policy: CommandPolicy | None = None,
    permission_handler: object | None = None,
) -> ToolExecutor:
    """创建绑定默认注册表的执行器。"""
    return ToolExecutor(
        create_default_registry(
            workspace=workspace,
            workspace_root=workspace_root,
            execution_service=execution_service,
            command_policy=command_policy,
            permission_handler=permission_handler,
        )
    )
