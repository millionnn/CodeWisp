"""MCP domain errors — structured; never crash the Agent Runtime."""

from __future__ import annotations


class MCPError(Exception):
    """MCP domain base error."""

    code: str = "MCP_ERROR"

    def __init__(self, message: str, *, code: str | None = None) -> None:
        super().__init__(message)
        if code:
            self.code = code


class MCPServerNotFoundError(MCPError):
    code = "MCP_SERVER_NOT_FOUND"


class MCPServerUnavailableError(MCPError):
    code = "MCP_SERVER_UNAVAILABLE"


class MCPConnectionFailedError(MCPError):
    code = "MCP_CONNECTION_FAILED"


class MCPInitializationFailedError(MCPError):
    code = "MCP_INITIALIZATION_FAILED"


class MCPToolNotFoundError(MCPError):
    code = "MCP_TOOL_NOT_FOUND"


class MCPToolCallFailedError(MCPError):
    code = "MCP_TOOL_CALL_FAILED"


class MCPInvalidConfigurationError(MCPError):
    code = "MCP_INVALID_CONFIGURATION"


class MCPProtocolError(MCPError):
    code = "MCP_PROTOCOL_ERROR"


class MCPTimeoutError(MCPError):
    code = "MCP_TIMEOUT"
