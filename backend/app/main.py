"""CodeWisp 程序入口。

组装：配置 → Workspace → SQLite → LLMClient → AgentService → CLI。

```text
CLI → AgentService → SessionService → AgentLoop
```

Workspace 来自「打开的目标项目」，不是 CodeWisp 安装目录。
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from backend.app.cli.interface import run_cli
from backend.app.llm.client import LLMConfig
from backend.app.llm.errors import CodeWispError, ConfigError
from backend.app.persistence.paths import default_db_path
from backend.app.persistence.store import SqliteStore
from backend.app.providers.defaults import DEFAULT_MODEL_ID, DEFAULT_PROVIDER_ID
from backend.app.providers.resolver import ModelResolver
from backend.app.services.agent_service import AgentService
from backend.app.workspace.errors import WorkspaceError
from backend.app.workspace.resolve import resolve_workspace_root


def _load_env() -> None:
    """加载 LLM 等配置（不代表 Workspace）。

    顺序：仓库根 ``.env`` → ``~/.codewisp/.env``（后加载不覆盖已有环境变量）。
    """
    codewisp_root = Path(__file__).resolve().parents[2]
    load_dotenv(codewisp_root / ".env")
    load_dotenv(Path.home() / ".codewisp" / ".env")


def _parse_args(argv: list[str] | None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="codewisp",
        description="CodeWisp Coding Agent CLI",
    )
    parser.add_argument(
        "--workspace",
        "-w",
        default=None,
        help=(
            "目标仓库根目录（Agent 要探索的项目）。"
            "优先级高于环境变量 CODEWISP_WORKSPACE 与当前工作目录。"
            "省略时：CODEWISP_WORKSPACE → cwd。"
        ),
    )
    parser.add_argument(
        "--max-steps",
        type=int,
        default=None,
        help="Agent 迭代预算（每次 LLM 调用计 1 步）。省略时使用默认值。",
    )
    parser.add_argument(
        "--db",
        default=None,
        help="SQLite 数据库路径。省略时：CODEWISP_DB → ~/.codewisp/codewisp.db",
    )
    parser.add_argument(
        "--session",
        default=None,
        help="恢复已有 Session ID（续跑）。省略则创建新 Session。",
    )
    parser.add_argument(
        "--title",
        default="CLI Session",
        help="新建 Session 的标题（默认: CLI Session）。",
    )
    parser.add_argument(
        "--provider-id",
        default=None,
        help=(
            f"Session provider_id（默认 {DEFAULT_PROVIDER_ID}；"
            "V0.7 Phase 2 经 ModelResolver 决定本次 LLM）。"
        ),
    )
    parser.add_argument(
        "--model-id",
        default=None,
        help=(
            f"Session model_id（默认取 LLM_MODEL 或 {DEFAULT_MODEL_ID}）。"
        ),
    )
    return parser.parse_args(argv)


def _resolve_db_path(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    env = (os.getenv("CODEWISP_DB") or "").strip()
    if env:
        return Path(env).expanduser()
    return default_db_path()


def main(argv: list[str] | None = None) -> int:
    """启动 CodeWisp CLI，返回进程退出码。"""
    args = _parse_args(argv)
    _load_env()

    store: SqliteStore | None = None
    try:
        workspace_root = resolve_workspace_root(explicit=args.workspace)
        # 启动时校验 LLM_API_KEY 等仍可用；每次 run 由 ModelResolver 按 Session 解析
        config = LLMConfig.from_env()
        db_path = _resolve_db_path(args.db)
        store = SqliteStore(db_path)
        store.connect()

        resolver = ModelResolver.create_default()
        loop_kwargs: dict = {"model_resolver": resolver}
        if args.max_steps is not None:
            loop_kwargs["max_steps"] = args.max_steps
        agents = AgentService(store, **loop_kwargs)

        provider_id = (args.provider_id or DEFAULT_PROVIDER_ID).strip()
        model_id = (args.model_id or config.model or DEFAULT_MODEL_ID).strip()

        return run_cli(
            agents,
            workspace_root=workspace_root,
            session_id=args.session,
            session_title=args.title,
            provider_id=provider_id,
            model_id=model_id,
        )
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 1
    except WorkspaceError as exc:
        print(f"Workspace 错误：{exc}", file=sys.stderr)
        return 1
    except CodeWispError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1
    finally:
        if store is not None:
            store.close()


if __name__ == "__main__":
    raise SystemExit(main())
