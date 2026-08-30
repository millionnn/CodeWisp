"""API 依赖与应用状态。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from backend.app.llm.client import LLMClient
from backend.app.persistence.paths import default_db_path
from backend.app.persistence.store import SqliteStore
from backend.app.providers.resolver import ModelResolver
from backend.app.services.agent_service import AgentService
from backend.app.session.service import SessionService


@dataclass
class AppState:
    store: SqliteStore
    sessions: SessionService
    agents: AgentService


def build_app_state(
    *,
    db_path: str | Path | None = None,
    llm: LLMClient | None = None,
    model_resolver: ModelResolver | None = None,
    max_steps: int | None = None,
) -> AppState:
    path: str | Path = db_path if db_path is not None else default_db_path()
    store = SqliteStore(path)
    store.connect()
    sessions = SessionService(store)
    kwargs: dict = {}
    if llm is not None:
        kwargs["llm"] = llm
    elif model_resolver is not None:
        kwargs["model_resolver"] = model_resolver
    else:
        kwargs["model_resolver"] = ModelResolver.create_default()
    if max_steps is not None:
        kwargs["max_steps"] = max_steps
    agents = AgentService(store, **kwargs)
    return AppState(store=store, sessions=sessions, agents=agents)


def get_app_state(request: Request) -> AppState:
    return request.app.state.codewisp


def get_session_service(request: Request) -> SessionService:
    return get_app_state(request).sessions


def get_agent_service(request: Request) -> AgentService:
    return get_app_state(request).agents
