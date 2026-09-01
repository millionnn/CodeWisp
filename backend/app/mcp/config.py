"""MCP config loader — filesystem only; secrets via env, never SQLite."""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

from backend.app.mcp.errors import MCPInvalidConfigurationError
from backend.app.mcp.models import MCPServerConfig, MCPTransportKind

_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}|\$([A-Za-z_][A-Za-z0-9_]*)")


def default_user_config_path() -> Path:
    return Path.home() / ".codewisp" / "config.json"


def workspace_mcp_config_path(workspace_root: str | Path) -> Path:
    return Path(workspace_root).expanduser().resolve() / ".codewisp" / "mcp.json"


def _expand_env_value(value: str) -> str:
    def repl(match: re.Match[str]) -> str:
        key = match.group(1) or match.group(2)
        return os.environ.get(key, "")

    return _ENV_REF.sub(repl, value)


def _parse_server_entry(server_id: str, raw: Any) -> MCPServerConfig:
    if not isinstance(raw, dict):
        raise MCPInvalidConfigurationError(
            f"MCP server '{server_id}' must be an object"
        )
    command = raw.get("command")
    if not isinstance(command, str) or not command.strip():
        raise MCPInvalidConfigurationError(
            f"MCP server '{server_id}' requires non-empty 'command'"
        )
    args_raw = raw.get("args") or []
    if not isinstance(args_raw, list):
        raise MCPInvalidConfigurationError(
            f"MCP server '{server_id}' args must be a list"
        )
    env_raw = raw.get("env") or {}
    if not isinstance(env_raw, dict):
        raise MCPInvalidConfigurationError(
            f"MCP server '{server_id}' env must be an object"
        )
    env: dict[str, str] = {}
    for k, v in env_raw.items():
        env[str(k)] = _expand_env_value(str(v))

    transport_raw = str(raw.get("transport") or "stdio").lower()
    try:
        transport = MCPTransportKind(transport_raw)
    except ValueError as exc:
        raise MCPInvalidConfigurationError(
            f"MCP server '{server_id}' unsupported transport: {transport_raw}"
        ) from exc

    cwd = raw.get("cwd")
    if cwd is not None:
        cwd = str(cwd)

    return MCPServerConfig(
        server_id=server_id.strip(),
        command=command.strip(),
        args=tuple(str(a) for a in args_raw),
        env=env,
        enabled=bool(raw.get("enabled", True)),
        transport=transport,
        cwd=cwd,
        name=str(raw["name"]).strip() if raw.get("name") else None,
    )


def _load_json_file(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise MCPInvalidConfigurationError(
            f"Invalid MCP config file {path}: {exc}"
        ) from exc
    if not isinstance(data, dict):
        raise MCPInvalidConfigurationError(f"MCP config root must be object: {path}")
    return data


def parse_mcp_servers_section(data: dict[str, Any]) -> dict[str, MCPServerConfig]:
    section = data.get("mcpServers")
    if section is None:
        return {}
    if not isinstance(section, dict):
        raise MCPInvalidConfigurationError("'mcpServers' must be an object")
    out: dict[str, MCPServerConfig] = {}
    for sid, entry in section.items():
        sid_s = str(sid).strip()
        if not sid_s:
            continue
        # Allowlist: only keys present in config become servers.
        out[sid_s] = _parse_server_entry(sid_s, entry)
    return out


def load_mcp_configs(
    *,
    workspace_root: str | Path | None = None,
    user_config_path: Path | None = None,
) -> dict[str, MCPServerConfig]:
    """Merge ~/.codewisp/config.json then workspace/.codewisp/mcp.json (workspace wins)."""
    merged: dict[str, MCPServerConfig] = {}
    user_path = user_config_path or default_user_config_path()
    try:
        merged.update(parse_mcp_servers_section(_load_json_file(user_path)))
    except MCPInvalidConfigurationError:
        # Missing/empty user config is fine; corrupt file should surface
        if user_path.is_file():
            raise

    if workspace_root is not None:
        ws_path = workspace_mcp_config_path(workspace_root)
        if ws_path.is_file():
            merged.update(parse_mcp_servers_section(_load_json_file(ws_path)))
    return merged


def write_example_workspace_mcp_config(workspace_root: str | Path, demo_script: Path) -> Path:
    """Helper for demos/tests: write a minimal mcp.json pointing at the demo server."""
    path = workspace_mcp_config_path(workspace_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "mcpServers": {
            "demo": {
                "command": "python3",
                "args": [str(demo_script.resolve())],
                "enabled": True,
                "transport": "stdio",
            }
        }
    }
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path
