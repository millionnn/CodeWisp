"""API 依赖与应用状态。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from backend.app.llm.client import LLMClient, LLMConfig
from backend.app.persistence.paths import default_db_path
from backend.app.persistence.store import SqliteStore
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
    max_steps: int | None = None,
) -> AppState:
    path: str | Path = db_path if db_path is not None else default_db_path()
    store = SqliteStore(path)
    store.connect()
    sessions = SessionService(store)
    client = llm if llm is not None else LLMClient(LLMConfig.from_env())
    kwargs: dict = {"llm": client}
    if max_steps is not None:
        kwargs["max_steps"] = max_steps
    agents = AgentService(store, **kwargs)
    return AppState(store=store, sessions=sessions, agents=agents)

#获取一个应用状态
def get_app_state(request: Request) -> AppState:
    return request.app.state.codewisp

#获取一个session服务
def get_session_service(request: Request) -> SessionService:
    return get_app_state(request).sessions

#获取一个agent服务
def get_agent_service(request: Request) -> AgentService:
    return get_app_state(request).agents
