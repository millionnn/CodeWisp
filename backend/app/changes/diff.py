"""文件级 Diff 与 unified diff 文本（语义无关）。"""

from __future__ import annotations

import difflib

from backend.app.changes.models import ChangeType, FileDiff, SnapshotFile, WorkspaceSnapshot

#比较两个版本，算出「新增 / 修改 / 删除」，并生成 diff 文本

#比较两个 Snapshot（或 path→SnapshotFile 映射）
def compute_file_diffs(
    before: WorkspaceSnapshot | dict[str, SnapshotFile],
    after: WorkspaceSnapshot | dict[str, SnapshotFile],
    *,
    include_unchanged: bool = False,
) -> list[FileDiff]:
    """比较两个 Snapshot（或 path→SnapshotFile 映射）。"""
    left = before.file_map() if isinstance(before, WorkspaceSnapshot) else dict(before)
    right = after.file_map() if isinstance(after, WorkspaceSnapshot) else dict(after)
    paths = sorted(set(left) | set(right))
    diffs: list[FileDiff] = []
    for path in paths:
        a = left.get(path)
        b = right.get(path)
        before_text = a.content if a and a.exists else None
        after_text = b.content if b and b.exists else None
        before_exists = bool(a and a.exists)
        after_exists = bool(b and b.exists)

        if not before_exists and after_exists:
            change = ChangeType.ADDED
        elif before_exists and not after_exists:
            change = ChangeType.DELETED
        elif before_exists and after_exists and before_text != after_text:
            change = ChangeType.MODIFIED
        else:
            change = ChangeType.UNCHANGED

        if change is ChangeType.UNCHANGED and not include_unchanged:
            continue
        diffs.append(
            FileDiff(
                path=path,
                change_type=change,
                before=before_text,
                after=after_text,
            )
        )
    return diffs

#生成统一 diff 文本；跳过 UNCHANGED。
def format_unified_diff(
    diffs: list[FileDiff],
    *,
    from_label: str = "a",
    to_label: str = "b",
) -> str:
    """生成统一 diff 文本；跳过 UNCHANGED。"""
    chunks: list[str] = []
    for item in diffs:
        if item.change_type is ChangeType.UNCHANGED:
            continue
        before_lines = (item.before or "").splitlines(keepends=True)
        after_lines = (item.after or "").splitlines(keepends=True)
        # 空文件 / 删除：difflib 需要至少能产出 header
        if before_lines and not before_lines[-1].endswith("\n"):
            before_lines[-1] += "\n"
        if after_lines and not after_lines[-1].endswith("\n"):
            after_lines[-1] += "\n"
        piece = difflib.unified_diff(
            before_lines,
            after_lines,
            fromfile=f"{from_label}/{item.path}",
            tofile=f"{to_label}/{item.path}",
            lineterm="\n",
        )
        text = "".join(piece)
        if text:
            chunks.append(text.rstrip("\n"))
        else:
            # 两边皆空但状态变化（极少）：仍标路径
            chunks.append(
                f"--- {from_label}/{item.path}\n"
                f"+++ {to_label}/{item.path}\n"
                f"# {item.change_type.value}"
            )
    return "\n".join(chunks)
