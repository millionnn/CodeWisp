"""resolve_workspace_root 优先级与语义测试。"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.app.workspace.errors import WorkspaceIOError
from backend.app.workspace.resolve import ENV_WORKSPACE_ROOT, resolve_workspace_root


def test_explicit_wins_over_env_and_cwd(tmp_path: Path) -> None:
    explicit = tmp_path / "project_a"
    env_dir = tmp_path / "project_b"
    cwd_dir = tmp_path / "project_c"
    for p in (explicit, env_dir, cwd_dir):
        p.mkdir()

    root = resolve_workspace_root(
        explicit=explicit,
        environ={ENV_WORKSPACE_ROOT: str(env_dir)},
        cwd=cwd_dir,
    )
    assert root == explicit.resolve()


def test_env_wins_over_cwd(tmp_path: Path) -> None:
    env_dir = tmp_path / "from_env"
    cwd_dir = tmp_path / "from_cwd"
    env_dir.mkdir()
    cwd_dir.mkdir()

    root = resolve_workspace_root(
        explicit=None,
        environ={ENV_WORKSPACE_ROOT: str(env_dir)},
        cwd=cwd_dir,
    )
    assert root == env_dir.resolve()


def test_fallback_to_cwd(tmp_path: Path) -> None:
    cwd_dir = tmp_path / "only_cwd"
    cwd_dir.mkdir()
    root = resolve_workspace_root(explicit=None, environ={}, cwd=cwd_dir)
    assert root == cwd_dir.resolve()


def test_missing_path_fails(tmp_path: Path) -> None:
    missing = tmp_path / "nope"
    with pytest.raises(WorkspaceIOError, match="不存在"):
        resolve_workspace_root(explicit=missing, environ={}, cwd=tmp_path)


def test_file_path_fails(tmp_path: Path) -> None:
    f = tmp_path / "file.txt"
    f.write_text("x", encoding="utf-8")
    with pytest.raises(WorkspaceIOError, match="不是文件夹"):
        resolve_workspace_root(explicit=f, environ={}, cwd=tmp_path)
