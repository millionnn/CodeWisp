"""Workspace 包。

Workspace = Agent 服务的目标仓库沙箱，与 CodeWisp 源码目录无关。
"""

from backend.app.workspace.errors import (
    PathOutsideWorkspaceError,
    WorkspaceError,
    WorkspaceIOError,
)
from backend.app.workspace.resolve import ENV_WORKSPACE_ROOT, resolve_workspace_root
from backend.app.workspace.workspace import Workspace

__all__ = [
    "ENV_WORKSPACE_ROOT",
    "PathOutsideWorkspaceError",
    "Workspace",
    "WorkspaceError",
    "WorkspaceIOError",
    "resolve_workspace_root",
]
