"""FastAPI 请求/响应 schema。"""
#各个api的请求的参数规范
from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.app.providers.defaults import DEFAULT_MODEL_ID, DEFAULT_PROVIDER_ID

#创建一个session请求
class CreateSessionRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    title: str = Field(..., min_length=1)
    workspace: str = Field(..., min_length=1)
    provider_id: str = DEFAULT_PROVIDER_ID
    model_id: str = DEFAULT_MODEL_ID

#更新一个session请求
class PatchSessionRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    title: str | None = None
    status: str | None = None
    provider_id: str | None = None
    model_id: str | None = None

#一个session响应
class SessionResponse(BaseModel):
    #获取模型配置
    model_config = ConfigDict(protected_namespaces=())

    session_id: str
    title: str
    workspace: str
    provider_id: str
    model_id: str
    status: str
    created_at: str | None = None
    updated_at: str | None = None

#发送一条消息请求
class PostMessageRequest(BaseModel):
    content: str = Field(..., min_length=1)

#一个工具调用请求
class ToolCallPayload(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    arguments_raw: str | None = None
    parse_error: str | None = None

#一条消息响应
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

#一个agent工作响应
class AgentRunResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

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

#一个agent工作步骤响应
class AgentStepResponse(BaseModel):
    step_id: str
    agent_run_id: str
    session_id: str
    step_index: int
    status: str
    created_at: str | None = None
    completed_at: str | None = None


class AgentEventResponse(BaseModel):
    event_type: str
    step: int
    timestamp: float
    tool_name: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


#发送一条消息响应
class PostMessageResponse(BaseModel):
    session: SessionResponse
    run: AgentRunResponse
    steps: list[AgentStepResponse]
    final_answer: str | None = None
    status: str
    termination_reason: str | None = None
    error: str | None = None
    messages: list[MessageResponse]
    events: list[AgentEventResponse] = Field(default_factory=list)


class PermissionRequestResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    request_id: str
    command: str
    args: list[str] = Field(default_factory=list)
    cwd: str
    reason: str = ""
    tool_name: str = "run_command"
    created_at: str | None = None
    session_id: str | None = None
    agent_run_id: str | None = None


class PermissionPendingResponse(BaseModel):
    pending: PermissionRequestResponse | None = None


class PermissionDecideRequest(BaseModel):
    request_id: str = Field(..., min_length=1)
    decision: str = Field(..., min_length=1, description="allow|deny|y|n|yes|no")


class ProviderResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    provider_id: str
    display_name: str
    capabilities: list[str] = Field(default_factory=list)
    model_ids: list[str] = Field(default_factory=list)
    credential_configured: bool = False


class ModelResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: str
    provider_id: str
    display_name: str
    context_window: int | None = None
    supports_tool_call: bool = True
    supports_streaming: bool = False
