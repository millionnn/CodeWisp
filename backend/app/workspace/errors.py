"""Workspace 相关异常。"""


class WorkspaceError(Exception):
    """Workspace 操作失败。"""


class PathOutsideWorkspaceError(WorkspaceError):
    """路径解析后超出 workspace 根目录。"""


class WorkspaceIOError(WorkspaceError):
    """读写或遍历失败（不存在、权限、二进制等）。"""
