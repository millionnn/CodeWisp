"""MCP Tool Extension Layer — dynamic tools via Model Context Protocol."""

from backend.app.mcp.adapter import MCPToolAdapter
from backend.app.mcp.errors import (
    MCPConnectionFailedError,
    MCPError,
    MCPInitializationFailedError,
    MCPInvalidConfigurationError,
    MCPProtocolError,
    MCPServerNotFoundError,
    MCPServerUnavailableError,
    MCPTimeoutError,
    MCPToolCallFailedError,
    MCPToolNotFoundError,
)
from backend.app.mcp.manager import MCPManager, get_manager_for_workspace
from backend.app.mcp.models import (
    MCPPermissionLevel,
    MCPServerConfig,
    MCPServerRuntime,
    MCPServerStatus,
    MCPToolInfo,
)
from backend.app.mcp.registry import sync_mcp_tools_to_registry
from backend.app.mcp.service import MCPService

__all__ = [
    "MCPToolAdapter",
    "MCPError",
    "MCPServerNotFoundError",
    "MCPServerUnavailableError",
    "MCPConnectionFailedError",
    "MCPInitializationFailedError",
    "MCPToolNotFoundError",
    "MCPToolCallFailedError",
    "MCPInvalidConfigurationError",
    "MCPProtocolError",
    "MCPTimeoutError",
    "MCPManager",
    "get_manager_for_workspace",
    "MCPPermissionLevel",
    "MCPServerConfig",
    "MCPServerRuntime",
    "MCPServerStatus",
    "MCPToolInfo",
    "sync_mcp_tools_to_registry",
    "MCPService",
]
