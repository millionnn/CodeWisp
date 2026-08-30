"""Interactive Permission REST（供未来 Web UI；CLI 不经 HTTP）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.deps import AppState, get_app_state, get_session_service
from backend.app.api.schemas import (
    PermissionDecideRequest,
    PermissionPendingResponse,
    PermissionRequestResponse,
)
from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.errors import (
    InvalidPermissionDecisionError,
    PermissionError,
)
from backend.app.session.service import SessionService

router = APIRouter(prefix="/api/sessions", tags=["permissions"])


def _to_response(req) -> PermissionRequestResponse:
    return PermissionRequestResponse(
        request_id=req.request_id,
        command=req.command,
        args=list(req.args),
        cwd=req.cwd,
        reason=req.reason,
        tool_name=req.tool_name,
        created_at=req.created_at,
        session_id=req.session_id,
        agent_run_id=req.agent_run_id,
    )


@router.get(
    "/{session_id}/permissions/pending",
    response_model=PermissionPendingResponse,
)
def get_pending_permission(
    session_id: str,
    state: AppState = Depends(get_app_state),
    sessions: SessionService = Depends(get_session_service),
) -> PermissionPendingResponse:
    sessions.get_session(session_id)  # 404 if missing
    pending = state.permission_broker.get_pending(session_id)
    if pending is None:
        return PermissionPendingResponse(pending=None)
    return PermissionPendingResponse(pending=_to_response(pending))


@router.post(
    "/{session_id}/permissions/decide",
    response_model=PermissionRequestResponse,
)
def decide_permission(
    session_id: str,
    body: PermissionDecideRequest,
    state: AppState = Depends(get_app_state),
    sessions: SessionService = Depends(get_session_service),
) -> PermissionRequestResponse:
    sessions.get_session(session_id)
    try:
        decision = PermissionDecision.parse(body.decision)
    except InvalidPermissionDecisionError as exc:
        raise PermissionError(str(exc)) from exc
    req = state.permission_broker.decide(
        session_id,
        request_id=body.request_id,
        decision=decision,
    )
    return _to_response(req)
