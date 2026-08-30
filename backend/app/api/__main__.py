"""可选入口：``python -m backend.app.api`` 启动 uvicorn。"""

from __future__ import annotations

import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv

from backend.app.banner import print_app_banner


def _load_env() -> None:
    """加载 CodeWisp 仓库根目录的 .env（与 CLI main 一致）。"""
    codewisp_root = Path(__file__).resolve().parents[3]
    load_dotenv(codewisp_root / ".env")


def main() -> None:
    _load_env()
    print_app_banner()
    host = os.getenv("CODEWISP_API_HOST", "127.0.0.1")
    port = int(os.getenv("CODEWISP_API_PORT", "8000"))
    print(f"  API listening on http://{host}:{port}")
    print(f"  Docs          http://{host}:{port}/docs\n")
    uvicorn.run(
        "backend.app.api.app:create_app",
        factory=True,
        host=host,
        port=port,
        reload=False,
    )


if __name__ == "__main__":
    main()
