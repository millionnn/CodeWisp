"""Session REST 路由。"""
#session相关的api具体定义
from __future__ import annotations

from fastapi import APIRouter, Depends, Response, status

from backend.app.api.deps import get_session_service
from backend.app.api.schemas import (
    CreateSessionRequest,
    PatchSessionRequest,
    SessionResponse,
)
from backend.app.api.serializers import session_to_response
from backend.app.session.errors import InvalidSessionError
from backend.app.session.service import SessionService

router = APIRouter(prefix="/api/sessions", tags=["sessions"])

#创建一个session：POST   /api/sessions
@router.post("", response_model=SessionResponse, status_code=status.HTTP_201_CREATED)
def create_session(
    body: CreateSessionRequest,
    sessions: SessionService = Depends(get_session_service),
) -> SessionResponse:
    session = sessions.create_session(
        title=body.title,
        workspace=body.workspace,
        provider_id=body.provider_id,
        model_id=body.model_id,
    )
    return session_to_response(session)

#获取所有session：GET   /api/sessions
@router.get("", response_model=list[SessionResponse])
def list_sessions(
    sessions: SessionService = Depends(get_session_service),
) -> list[SessionResponse]:
    return [session_to_response(s) for s in sessions.list_sessions()]

#获取一个session：GET   /api/sessions/{session_id}
@router.get("/{session_id}", response_model=SessionResponse)
def get_session(
    session_id: str,
    sessions: SessionService = Depends(get_session_service),
) -> SessionResponse:
    return session_to_response(sessions.get_session(session_id))

#更新一个session：PATCH   /api/sessions/{session_id}
@router.patch("/{session_id}", response_model=SessionResponse)
def patch_session(
    session_id: str,
    body: PatchSessionRequest,
    sessions: SessionService = Depends(get_session_service),
) -> SessionResponse:
    if (
        body.title is None
        and body.status is None
        and body.provider_id is None
        and body.model_id is None
    ):
        raise InvalidSessionError("PATCH 至少需要提供一个可更新字段")
    session = sessions.update_session(
        session_id,
        title=body.title,
        status=body.status,
        provider_id=body.provider_id,
        model_id=body.model_id,
    )
    return session_to_response(session)

#删除一个session：DELETE   /api/sessions/{session_id}
@router.delete(
    "/{session_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
)
def delete_session(
    session_id: str,
    sessions: SessionService = Depends(get_session_service),
) -> Response:
    sessions.delete_session(session_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
