"""FastAPI 应用工厂。

```text
HTTP → SessionService / AgentService → AgentLoop
```

不在本层重新实现 LLM / Tool 循环。
"""

#在这里给cli和web端提供api

from __future__ import annotations

from contextlib import asynccontextmanager
from pathlib import Path
from typing import AsyncIterator

from fastapi import FastAPI

from backend.app.api.deps import AppState, build_app_state
from backend.app.api.errors import register_exception_handlers
from backend.app.api.routes import changes, messages, permissions, providers, sessions
from backend.app.llm.client import LLMClient


def _ensure_env_loaded() -> None:
    """工厂入口也可能被直接 import；保证 .env 已加载。"""
    from pathlib import Path

    from dotenv import load_dotenv

    codewisp_root = Path(__file__).resolve().parents[3]
    load_dotenv(codewisp_root / ".env")


def create_app(
    *,
    db_path: str | Path | None = None,
    llm: LLMClient | None = None,
    max_steps: int | None = None,
    state: AppState | None = None,
) -> FastAPI:
    """创建 FastAPI app；测试可注入 ``state`` / ``llm`` / 内存库路径。"""
    from backend.app.banner import APP_NAME, TAGLINE, __version__, format_banner

    _ensure_env_loaded()

    app_state = state or build_app_state(
        db_path=db_path,
        llm=llm,
        max_steps=max_steps,
    )

    #生命周期管理，在应用启动和关闭时执行
    @asynccontextmanager
    async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
        yield
        app_state.store.close()

    app = FastAPI(
        title=APP_NAME,
        version=__version__,
        description=f"{TAGLINE}\n\n{format_banner(include_meta=True)}",
        lifespan=lifespan,
    )
    register_exception_handlers(app)
    app.state.codewisp = app_state

    app.include_router(sessions.router)
    app.include_router(messages.router)
    app.include_router(permissions.router)
    app.include_router(providers.router)
    app.include_router(changes.router)

    @app.get("/health")
    def health() -> dict[str, str]:
        return {
            "status": "ok",
            "app": APP_NAME,
            "version": __version__,
        }

    return app
