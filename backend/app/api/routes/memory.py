"""Memory / Plan / Context HTTP 边界（供未来 Web UI）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.deps import get_agent_service
from backend.app.services.agent_service import AgentService
from backend.app.session.errors import SessionNotFoundError

router = APIRouter(tags=["memory"])


@router.get("/api/sessions/{session_id}/memories")
def list_memories(
    session_id: str,
    agents: AgentService = Depends(get_agent_service),
) -> dict:
    try:
        items = agents.list_memories(session_id)
        return {"memories": [m.to_dict() for m in items]}
    except SessionNotFoundError:
        raise


@router.get("/api/sessions/{session_id}/memories/search")
def search_memories(
    session_id: str,
    q: str = "",
    top_k: int = 10,
    agents: AgentService = Depends(get_agent_service),
) -> dict:
    hits = agents.memory_search(session_id, q, top_k=top_k)
    return {"query": q, "results": [h.to_dict() for h in hits]}


@router.post("/api/sessions/{session_id}/memory/reindex")
def reindex_memory(
    session_id: str,
    agents: AgentService = Depends(get_agent_service),
) -> dict:
    stats = agents.memory_index(session_id)
    return {"stats": stats.to_dict()}


@router.get("/api/sessions/{session_id}/plans")
def list_plans(
    session_id: str,
    agents: AgentService = Depends(get_agent_service),
) -> dict:
    plans = agents.list_plans(session_id)
    return {"plans": [p.to_dict() for p in plans]}


@router.get("/api/sessions/{session_id}/context")
def get_context(
    session_id: str,
    agents: AgentService = Depends(get_agent_service),
) -> dict:
    return agents.get_context_bundle(session_id)
