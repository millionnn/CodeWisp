"""将 Snapshot 应用到 Workspace（唯一写回入口）。"""

from __future__ import annotations

from backend.app.changes.errors import RestoreError
from backend.app.changes.models import RestoreReport, WorkspaceSnapshot
from backend.app.workspace.errors import WorkspaceError
from backend.app.workspace.workspace import Workspace


def apply_snapshot_to_workspace(
    workspace: Workspace,
    snapshot: WorkspaceSnapshot,
) -> RestoreReport:
    """按 SnapshotFile 写回/删除；全部经 Workspace 边界与原子写。"""
    if snapshot.workspace_root != str(workspace.root):
        raise RestoreError(
            "Snapshot workspace_root 与当前 Workspace 不一致："
            f"{snapshot.workspace_root!r} vs {str(workspace.root)!r}"
        )

    applied: list[str] = []
    failed: list[tuple[str, str]] = []
    for item in snapshot.files:
        try:
            # 再次校验 path 落在边界内
            workspace.resolve_path(item.path)
            if item.exists:
                if item.content is None:
                    raise RestoreError(f"Snapshot 文件缺少 content: {item.path}")
                workspace.write_text(
                    item.path,
                    item.content,
                    overwrite=True,
                    create_parents=True,
                )
            else:
                workspace.delete_file(item.path)
            applied.append(item.path)
        except (WorkspaceError, OSError, RestoreError) as exc:
            failed.append((item.path, str(exc)))

    report = RestoreReport(
        snapshot_id=snapshot.snapshot_id,
        applied=tuple(applied),
        failed=tuple(failed),
    )
    if failed and not applied:
        raise RestoreError(
            f"Restore 全部失败: {snapshot.snapshot_id}; {failed[0][1]}"
        )
    return report
