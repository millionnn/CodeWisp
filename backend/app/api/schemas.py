"""FastAPI 请求/响应 schema。"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class CreateSessionRequest(BaseModel):
    title: str = Field(..., min_length=1)
    workspace: str = Field(..., min_length=1)
    provider_id: str = "deepseek"
    model_id: str = "deepseek-chat"


class PatchSessionRequest(BaseModel):
    title: str | None = None
    status: str | None = None
    provider_id: str | None = None
    model_id: str | None = None


class SessionResponse(BaseModel):
    session_id: str
    title: str
    workspace: str
    provider_id: str
    model_id: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None


class PostMessageRequest(BaseModel):
    content: str = Field(..., min_length=1)


class ToolCallPayload(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    arguments_raw: str | None = None
    parse_error: str | None = None


class MessageResponse(BaseModel):
    message_id: str | None = None
    session_id: str | None = None
    agent_run_id: str | None = None
    step_id: str | None = None
    seq: int | None = None
    role: str
    content: str | None = None
    tool_call_id: str | None = None
    tool_calls: list[ToolCallPayload] = Field(default_factory=list)
    created_at: str | None = None


class AgentRunResponse(BaseModel):
    agent_run_id: str
    session_id: str
    provider_id: str
    model_id: str
    status: str
    termination_reason: str | None = None
    max_steps: int
    final_answer: str | None = None
    error: str | None = None
    created_at: str | None = None
    completed_at: str | None = None


class AgentStepResponse(BaseModel):
    step_id: str
    agent_run_id: str
    session_id: str
    step_index: int
    status: str
    created_at: str | None = None
    completed_at: str | None = None


class PostMessageResponse(BaseModel):
    session: SessionResponse
    run: AgentRunResponse
    steps: list[AgentStepResponse]
    final_answer: str | None = None
    status: str
    termination_reason: str | None = None
    error: str | None = None
    messages: list[MessageResponse]
