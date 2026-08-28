"""CodeWisp 程序入口。

组装：配置 → LLMClient → Tool System → AgentLoop → CLI。
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

from backend.app.agent.loop import AgentLoop
from backend.app.cli.interface import run_cli
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import CodeWispError, ConfigError
from backend.app.tools.factory import create_default_registry
from backend.app.tools.executor import ToolExecutor


def _load_env() -> None:
    """若项目根目录存在 .env 则加载（不覆盖已有真实环境变量）。"""
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")


def main(argv: list[str] | None = None) -> int:
    """启动 CodeWisp CLI，返回进程退出码。"""
    _ = argv
    _load_env()

    try:
        config = LLMConfig.from_env()
        client = LLMClient(config)
        registry = create_default_registry()
        executor = ToolExecutor(registry)
        agent = AgentLoop(client, executor, registry)
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 1
    except CodeWispError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    try:
        return run_cli(agent)
    except CodeWispError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
