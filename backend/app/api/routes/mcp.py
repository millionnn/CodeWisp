"""V1.3 MCP REST API — goes through AgentService / MCPService only."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from backend.app.api.deps import get_agent_service, get_session_service
from backend.app.mcp.errors import MCPError
from backend.app.services.agent_service import AgentService
from backend.app.session.errors import InvalidSessionError
from backend.app.session.service import SessionService

router = APIRouter(tags=["mcp"])


class MCPToolResponse(BaseModel):
    server_id: str
    tool_name: str
    tool_id: str
    description: str = ""
    permission_level: str = "ask"
    enabled: bool = True
    input_schema: dict[str, Any] = Field(default_factory=dict)


class MCPServerResponse(BaseModel):
    server_id: str
    name: str
    command: str
    args: list[str] = Field(default_factory=list)
    enabled: bool = True
    transport: str = "stdio"
    status: str
    message: str = ""
    connected: bool = False
    tool_count: int = 0
    tools: list[MCPToolResponse] = Field(default_factory=list)
    env_keys: list[str] = Field(default_factory=list)


class MCPServersResponse(BaseModel):
    servers: list[MCPServerResponse] = Field(default_factory=list)


class MCPToolsResponse(BaseModel):
    server_id: str
    tools: list[MCPToolResponse] = Field(default_factory=list)


class MCPCallRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)
    confirm: bool = False


class MCPCallResponse(BaseModel):
    success: bool
    content: str = ""
    error: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


def _server_resp(data: dict[str, Any]) -> MCPServerResponse:
    tools = [
        MCPToolResponse(**t) if isinstance(t, dict) else t
        for t in (data.get("tools") or [])
    ]
    return MCPServerResponse(
        server_id=str(data.get("server_id") or ""),
        name=str(data.get("name") or data.get("server_id") or ""),
        command=str(data.get("command") or ""),
        args=list(data.get("args") or []),
        enabled=bool(data.get("enabled", True)),
        transport=str(data.get("transport") or "stdio"),
        status=str(data.get("status") or "configured"),
        message=str(data.get("message") or ""),
        connected=bool(data.get("connected")),
        tool_count=int(data.get("tool_count") or len(tools)),
        tools=tools,
        env_keys=list(data.get("env_keys") or []),
    )


@router.get("/api/mcp/servers", response_model=MCPServersResponse)
def list_mcp_servers_global(
    session_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> MCPServersResponse:
    """List MCP servers for a session workspace (query: session_id)."""
    sessions.get_session(session_id)
    servers = agents.mcp_list_servers(session_id)
    return MCPServersResponse(servers=[_server_resp(s.to_dict()) for s in servers])


@router.get(
    "/api/sessions/{session_id}/mcp/servers",
    response_model=MCPServersResponse,
)
def list_mcp_servers(
    session_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> MCPServersResponse:
    sessions.get_session(session_id)
    servers = agents.mcp_list_servers(session_id)
    return MCPServersResponse(servers=[_server_resp(s.to_dict()) for s in servers])


@router.get(
    "/api/sessions/{session_id}/mcp/servers/{server_id}",
    response_model=MCPServerResponse,
)
def get_mcp_server(
    session_id: str,
    server_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> MCPServerResponse:
    sessions.get_session(session_id)
    try:
        rt = agents.mcp_get_server(session_id, server_id)
    except MCPError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return _server_resp(rt.to_dict())


@router.get(
    "/api/sessions/{session_id}/mcp/servers/{server_id}/tools",
    response_model=MCPToolsResponse,
)
def list_mcp_server_tools(
    session_id: str,
    server_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> MCPToolsResponse:
    sessions.get_session(session_id)
    try:
        tools = agents.mcp_list_tools(session_id, server_id=server_id)
    except MCPError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return MCPToolsResponse(
        server_id=server_id,
        tools=[MCPToolResponse(**t.to_dict()) for t in tools],
    )


@router.post(
    "/api/sessions/{session_id}/mcp/servers/{server_id}/connect",
    response_model=MCPServerResponse,
)
def connect_mcp_server(
    session_id: str,
    server_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> MCPServerResponse:
    sessions.get_session(session_id)
    try:
        rt = agents.mcp_connect(session_id, server_id)
    except MCPError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return _server_resp(rt.to_dict())


@router.post(
    "/api/sessions/{session_id}/mcp/servers/{server_id}/disconnect",
    response_model=MCPServerResponse,
)
def disconnect_mcp_server(
    session_id: str,
    server_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> MCPServerResponse:
    sessions.get_session(session_id)
    try:
        rt = agents.mcp_disconnect(session_id, server_id)
    except MCPError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return _server_resp(rt.to_dict())


@router.post(
    "/api/sessions/{session_id}/mcp/reload",
    response_model=MCPServersResponse,
)
def reload_mcp(
    session_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> MCPServersResponse:
    sessions.get_session(session_id)
    try:
        servers = agents.mcp_reload(session_id)
    except MCPError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return MCPServersResponse(servers=[_server_resp(s.to_dict()) for s in servers])


@router.post("/api/mcp/reload", response_model=MCPServersResponse)
def reload_mcp_global(
    session_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> MCPServersResponse:
    sessions.get_session(session_id)
    try:
        servers = agents.mcp_reload(session_id)
    except MCPError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return MCPServersResponse(servers=[_server_resp(s.to_dict()) for s in servers])


@router.post(
    "/api/sessions/{session_id}/mcp/servers/{server_id}/tools/{tool_name}/call",
    response_model=MCPCallResponse,
)
def call_mcp_tool(
    session_id: str,
    server_id: str,
    tool_name: str,
    body: MCPCallRequest,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> MCPCallResponse:
    sessions.get_session(session_id)
    try:
        result = agents.mcp_call_tool(
            session_id,
            server_id,
            tool_name,
            body.arguments,
            confirm=body.confirm,
        )
    except MCPError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return MCPCallResponse(
        success=result.success,
        content=result.content,
        error=result.error,
        metadata=dict(result.metadata),
    )


# Spec aliases at /api/mcp/*
@router.get("/api/mcp/servers/{server_id}", response_model=MCPServerResponse)
def get_mcp_server_global(
    server_id: str,
    session_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> MCPServerResponse:
    sessions.get_session(session_id)
    try:
        rt = agents.mcp_get_server(session_id, server_id)
    except MCPError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return _server_resp(rt.to_dict())


@router.get(
    "/api/mcp/servers/{server_id}/tools",
    response_model=MCPToolsResponse,
)
def list_mcp_tools_global(
    server_id: str,
    session_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> MCPToolsResponse:
    sessions.get_session(session_id)
    try:
        tools = agents.mcp_list_tools(session_id, server_id=server_id)
    except MCPError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return MCPToolsResponse(
        server_id=server_id,
        tools=[MCPToolResponse(**t.to_dict()) for t in tools],
    )


@router.post(
    "/api/mcp/servers/{server_id}/connect",
    response_model=MCPServerResponse,
)
def connect_mcp_global(
    server_id: str,
    session_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> MCPServerResponse:
    sessions.get_session(session_id)
    try:
        rt = agents.mcp_connect(session_id, server_id)
    except MCPError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return _server_resp(rt.to_dict())


@router.post(
    "/api/mcp/servers/{server_id}/disconnect",
    response_model=MCPServerResponse,
)
def disconnect_mcp_global(
    server_id: str,
    session_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> MCPServerResponse:
    sessions.get_session(session_id)
    try:
        rt = agents.mcp_disconnect(session_id, server_id)
    except MCPError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return _server_resp(rt.to_dict())
