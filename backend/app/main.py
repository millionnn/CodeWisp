"""CodeWisp 程序入口。

组装：配置 → 解析目标 Workspace → LLMClient → Tool System → AgentLoop → CLI。

Workspace 来自「打开的目标项目」，不是 CodeWisp 安装目录。
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from dotenv import load_dotenv

from backend.app.agent.loop import AgentLoop
from backend.app.cli.interface import run_cli
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import CodeWispError, ConfigError
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry
from backend.app.workspace.errors import WorkspaceError
from backend.app.workspace.resolve import resolve_workspace_root


def _load_env() -> None:
    """若 CodeWisp 仓库根存在 .env 则加载（仅加载配置，不代表 Workspace）。"""
    codewisp_root = Path(__file__).resolve().parents[2]
    load_dotenv(codewisp_root / ".env")


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
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """启动 CodeWisp CLI，返回进程退出码。"""
    args = _parse_args(argv)
    _load_env()

    try:
        workspace_root = resolve_workspace_root(explicit=args.workspace)
        config = LLMConfig.from_env()
        client = LLMClient(config)
        registry = create_default_registry(workspace_root=workspace_root)
        executor = ToolExecutor(registry)
        loop_kwargs: dict = {}
        if args.max_steps is not None:
            loop_kwargs["max_steps"] = args.max_steps
        agent = AgentLoop(client, executor, registry, **loop_kwargs)
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 1
    except WorkspaceError as exc:
        print(f"Workspace 错误：{exc}", file=sys.stderr)
        return 1
    except CodeWispError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    try:
        return run_cli(agent, workspace_root=workspace_root)
    except CodeWispError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
