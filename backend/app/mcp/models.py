"""MCP domain models — config vs runtime status separated; no secrets."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class MCPTransportKind(str, Enum):
    STDIO = "stdio"


class MCPServerStatus(str, Enum):
    CONFIGURED = "configured"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    DISCONNECTED = "disconnected"
    ERROR = "error"
    DISABLED = "disabled"


class MCPPermissionLevel(str, Enum):
    ALLOW = "allow"
    ASK = "ask"
    DENY = "deny"


@dataclass(frozen=True)
class MCPServerConfig:
    """Filesystem config entry (secrets via env expansion only; never persisted to SQLite)."""

    server_id: str
    command: str
    args: tuple[str, ...] = ()
    env: dict[str, str] = field(default_factory=dict)
    enabled: bool = True
    transport: MCPTransportKind = MCPTransportKind.STDIO
    cwd: str | None = None
    name: str | None = None

    @property
    def display_name(self) -> str:
        return self.name or self.server_id

    def to_dict(self, *, include_env: bool = False) -> dict[str, Any]:
        data: dict[str, Any] = {
            "server_id": self.server_id,
            "name": self.display_name,
            "command": self.command,
            "args": list(self.args),
            "enabled": self.enabled,
            "transport": self.transport.value,
            "cwd": self.cwd,
        }
        if include_env:
            # Never dump raw values that look like secrets in API/CLI by default.
            data["env_keys"] = sorted(self.env.keys())
        else:
            data["env_keys"] = sorted(self.env.keys())
        return data


@dataclass
class MCPToolInfo:
    """Discovered tool from tools/list (raw MCP schema preserved)."""

    server_id: str
    tool_name: str
    description: str = ""
    input_schema: dict[str, Any] = field(default_factory=dict)
    permission_level: MCPPermissionLevel = MCPPermissionLevel.ASK
    enabled: bool = True
    annotations: dict[str, Any] = field(default_factory=dict)

    @property
    def tool_id(self) -> str:
        return f"mcp.{self.server_id}.{self.tool_name}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "tool_name": self.tool_name,
            "tool_id": self.tool_id,
            "description": self.description,
            "input_schema": dict(self.input_schema),
            "permission_level": self.permission_level.value,
            "enabled": self.enabled,
            "annotations": dict(self.annotations),
        }


@dataclass
class MCPResourceInfo:
    """Reserved for Future: resources/list + resources/read."""

    server_id: str
    uri: str
    name: str = ""
    description: str = ""
    mime_type: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "server_id": self.server_id,
            "uri": self.uri,
            "name": self.name,
            "description": self.description,
            "mime_type": self.mime_type,
        }


@dataclass
class MCPServerRuntime:
    """Runtime status for one configured server (no secrets)."""

    config: MCPServerConfig
    status: MCPServerStatus = MCPServerStatus.CONFIGURED
    message: str = ""
    tools: list[MCPToolInfo] = field(default_factory=list)
    protocol_version: str | None = None

    @property
    def server_id(self) -> str:
        return self.config.server_id

    @property
    def connected(self) -> bool:
        return self.status is MCPServerStatus.CONNECTED

    def to_dict(self) -> dict[str, Any]:
        return {
            **self.config.to_dict(include_env=False),
            "status": self.status.value,
            "message": self.message,
            "connected": self.connected,
            "tool_count": len(self.tools),
            "tools": [t.to_dict() for t in self.tools],
            "protocol_version": self.protocol_version,
        }

    def render_line(self) -> str:
        if not self.config.enabled:
            mark = "✗"
            label = "disabled"
        elif self.status is MCPServerStatus.CONNECTED:
            mark = "✓"
            label = "connected"
        elif self.status is MCPServerStatus.ERROR:
            mark = "⚠"
            label = "error"
        else:
            mark = "○"
            label = self.status.value
        n = len(self.tools)
        extra = f"  {n} tools" if n else ""
        if self.message and self.status is MCPServerStatus.ERROR:
            extra = f"  {self.message[:60]}"
        return f"{mark} {self.config.display_name}\n  {label}{extra}"


@dataclass(frozen=True)
class MCPCallResult:
    success: bool
    content: str
    error: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "content": self.content,
            "error": self.error,
            "metadata": dict(self.metadata),
        }
