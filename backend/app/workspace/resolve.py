"""解析 Agent 所服务的「目标仓库」根目录。

Workspace ≠ CodeWisp 源码目录。
Workspace 是用户打开/绑定的那个项目根（未来 Web UI 的 session.workspace_root）。

解析优先级（从高到低）：
1. 显式参数（CLI --workspace / 未来 API / Session 传入）
2. 环境变量 CODEWISP_WORKSPACE
3. 当前工作目录 cwd

这样：
- 短期：cd 到任意项目再启动，或 --workspace / .env 指定，即可测试
- 长期：Web UI 只需把「当前打开的项目路径」作为显式参数注入，无需改 Tool/AgentLoop
"""

from __future__ import annotations

import os
from pathlib import Path

from backend.app.workspace.errors import WorkspaceIOError

ENV_WORKSPACE_ROOT = "CODEWISP_WORKSPACE"


def resolve_workspace_root(
    *,
    explicit: str | Path | None = None,
    environ: dict[str, str] | None = None,
    cwd: str | Path | None = None,
) -> Path:
    """解析并校验目标仓库根目录，返回 resolve 后的绝对路径。"""
    env = environ if environ is not None else os.environ
    candidates: list[tuple[str, str | Path]] = []

    if explicit is not None and str(explicit).strip():
        candidates.append(("explicit", str(explicit).strip()))

    env_value = (env.get(ENV_WORKSPACE_ROOT) or "").strip()
    if env_value:
        candidates.append((f"env:{ENV_WORKSPACE_ROOT}", env_value))

    base_cwd = Path.cwd() if cwd is None else Path(cwd)
    candidates.append(("cwd", base_cwd))

    source, raw = candidates[0]
    root = Path(raw).expanduser()
    try:
        resolved = root.resolve()
    except OSError as exc:
        raise WorkspaceIOError(f"无法解析 Workspace 路径（{source}）：{raw}（{exc}）") from exc

    if not resolved.exists():
        raise WorkspaceIOError(f"Workspace 根目录不存在（{source}）：{resolved}")
    if not resolved.is_dir():
        raise WorkspaceIOError(f"Workspace 根目录不是文件夹（{source}）：{resolved}")
    return resolved
