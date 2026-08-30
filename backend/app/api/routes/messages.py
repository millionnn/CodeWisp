"""Conversation / Agent Message REST 路由。"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.deps import get_agent_service, get_session_service
from backend.app.api.schemas import MessageResponse, PostMessageRequest, PostMessageResponse
from backend.app.api.serializers import (
    agent_result_to_response,
    message_to_response,
)
from backend.app.services.agent_service import AgentService
from backend.app.session.service import SessionService

router = APIRouter(prefix="/api/sessions", tags=["messages"])


@router.get("/{session_id}/messages", response_model=list[MessageResponse])
def list_messages(
    session_id: str,
    sessions: SessionService = Depends(get_session_service),
) -> list[MessageResponse]:
    conversation = sessions.load_conversation(session_id)
    return [message_to_response(m) for m in conversation.messages]


@router.post("/{session_id}/messages", response_model=PostMessageResponse)
def post_message(
    session_id: str,
    body: PostMessageRequest,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> PostMessageResponse:
    """经 AgentService → AgentLoop 执行用户消息并持久化。"""
    result = agents.run(session_id, body.content)
    messages = sessions.load_conversation(session_id).messages
    return agent_result_to_response(result, messages=list(messages))
