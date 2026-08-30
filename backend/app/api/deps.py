"""API 依赖与应用状态。"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from fastapi import Request

from backend.app.llm.client import LLMClient
from backend.app.persistence.paths import default_db_path
from backend.app.persistence.store import SqliteStore
from backend.app.permissions.broker import BrokerPermissionHandler, PendingPermissionBroker
from backend.app.providers.resolver import ModelResolver
from backend.app.services.agent_service import AgentService
from backend.app.session.service import SessionService


@dataclass
class AppState:
    store: SqliteStore
    sessions: SessionService
    agents: AgentService
    permission_broker: PendingPermissionBroker
    model_resolver: ModelResolver


def build_app_state(
    *,
    db_path: str | Path | None = None,
    llm: LLMClient | None = None,
    model_resolver: ModelResolver | None = None,
    max_steps: int | None = None,
    permission_broker: PendingPermissionBroker | None = None,
) -> AppState:
    path: str | Path = db_path if db_path is not None else default_db_path()
    store = SqliteStore(path)
    store.connect()
    sessions = SessionService(store)
    resolver = model_resolver or ModelResolver.create_default()
    broker = permission_broker or PendingPermissionBroker()
    handler = BrokerPermissionHandler(broker)

    kwargs: dict = {
        "permission_handler": handler,
        "model_resolver": resolver,
    }
    if llm is not None:
        # 测试注入：固定 LLM，优先于 resolver（见 AgentService._resolve_runtime）
        # 使用 llm_factory 保持 ScriptedLLM，同时保留 Registry 供 /api/providers
        def _fixed_llm(_session):  # type: ignore[no-untyped-def]
            return llm

        kwargs["llm_factory"] = _fixed_llm
    if max_steps is not None:
        kwargs["max_steps"] = max_steps
    agents = AgentService(store, **kwargs)
    return AppState(
        store=store,
        sessions=sessions,
        agents=agents,
        permission_broker=broker,
        model_resolver=resolver,
    )


def get_app_state(request: Request) -> AppState:
    return request.app.state.codewisp


def get_session_service(request: Request) -> SessionService:
    return get_app_state(request).sessions


def get_agent_service(request: Request) -> AgentService:
    return get_app_state(request).agents
