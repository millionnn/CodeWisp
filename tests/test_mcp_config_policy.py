"""MCP domain / config / policy tests."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from backend.app.mcp.config import load_mcp_configs, parse_mcp_servers_section
from backend.app.mcp.errors import MCPInvalidConfigurationError
from backend.app.mcp.models import MCPPermissionLevel
from backend.app.mcp.policy import MCPPolicyAction, MCPToolPolicy, classify_mcp_tool


def test_parse_mcp_servers_section(tmp_path: Path) -> None:
    data = {
        "mcpServers": {
            "demo": {
                "command": "python3",
                "args": ["-m", "backend.app.mcp.demo_server"],
                "enabled": True,
            }
        }
    }
    configs = parse_mcp_servers_section(data)
    assert "demo" in configs
    assert configs["demo"].command == "python3"
    assert configs["demo"].enabled is True


def test_load_workspace_mcp_json(tmp_path: Path) -> None:
    cfg_dir = tmp_path / ".codewisp"
    cfg_dir.mkdir()
    (cfg_dir / "mcp.json").write_text(
        json.dumps(
            {
                "mcpServers": {
                    "filesystem": {
                        "command": "npx",
                        "args": ["-y", "server"],
                        "env": {"TOKEN": "${MISSING_ENV_VAR_XYZ}"},
                    }
                }
            }
        ),
        encoding="utf-8",
    )
    loaded = load_mcp_configs(
        workspace_root=tmp_path,
        user_config_path=tmp_path / "no-user.json",
    )
    assert loaded["filesystem"].env["TOKEN"] == ""


def test_invalid_config_raises() -> None:
    with pytest.raises(MCPInvalidConfigurationError):
        parse_mcp_servers_section({"mcpServers": {"x": {"command": ""}}})


def test_classify_permissions() -> None:
    assert classify_mcp_tool("search_project_docs") is MCPPermissionLevel.ALLOW
    assert classify_mcp_tool("get_issue") is MCPPermissionLevel.ALLOW
    assert classify_mcp_tool("create_issue") is MCPPermissionLevel.ASK
    assert classify_mcp_tool("delete_file") is MCPPermissionLevel.ASK
    assert classify_mcp_tool("shell_exec") is MCPPermissionLevel.DENY
    assert (
        classify_mcp_tool("weird", annotations={"readOnlyHint": True})
        is MCPPermissionLevel.ALLOW
    )
    assert (
        classify_mcp_tool("weird", annotations={"destructiveHint": True})
        is MCPPermissionLevel.DENY
    )


def test_policy_decide() -> None:
    policy = MCPToolPolicy()
    d = policy.decide("search_notes")
    assert d.action is MCPPolicyAction.ALLOW
    d2 = policy.decide("write_note")
    assert d2.action is MCPPolicyAction.ASK
    d3 = policy.decide("bash_shell")
    assert d3.action is MCPPolicyAction.DENY
