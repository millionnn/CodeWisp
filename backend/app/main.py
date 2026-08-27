"""CodeWisp 程序入口。

组装配置、LLM 客户端与 CLI。
核心 LLM 逻辑位于 backend.app.llm；本文件只做接线。
"""

from __future__ import annotations

import sys
from pathlib import Path

from dotenv import load_dotenv

from backend.app.cli.interface import run_cli
from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.llm.errors import CodeWispError, ConfigError


def _load_env() -> None:
    """若项目根目录存在 .env 则加载（不覆盖已有真实环境变量）。"""
    # backend/app/main.py -> parents[2] 为项目根目录
    project_root = Path(__file__).resolve().parents[2]
    load_dotenv(project_root / ".env")


def main(argv: list[str] | None = None) -> int:
    """启动 CodeWisp CLI，返回进程退出码。"""
    _ = argv  # 预留给未来命令行参数
    _load_env()

    try:
        config = LLMConfig.from_env()
        client = LLMClient(config)
    except ConfigError as exc:
        print(f"配置错误：{exc}", file=sys.stderr)
        return 1
    except CodeWispError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1

    try:
        return run_cli(client)
    except CodeWispError as exc:
        print(f"错误：{exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
