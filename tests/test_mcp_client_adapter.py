"""MCP client / adapter / registry / manager tests."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

from backend.app.mcp.adapter import MCPToolAdapter
from backend.app.mcp.client import FakeMCPClient, StdioMCPClient
from backend.app.mcp.manager import MCPManager, reset_managers_for_tests
from backend.app.mcp.models import (
    MCPPermissionLevel,
    MCPServerConfig,
    MCPToolInfo,
)
from backend.app.mcp.registry import sync_mcp_tools_to_registry, unregister_mcp_tools
from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.handler import ScriptedPermissionHandler
from backend.app.tools.builtin.calculator import CalculatorTool
from backend.app.tools.registry import ToolRegistry


@pytest.fixture(autouse=True)
def _reset_mcp() -> None:
    reset_managers_for_tests()
    yield
    reset_managers_for_tests()


def test_fake_client_list_and_call() -> None:
    tools = [
        MCPToolInfo(
            server_id="demo",
            tool_name="search_project_docs",
            description="search",
            permission_level=MCPPermissionLevel.ALLOW,
        )
    ]
    client = FakeMCPClient("demo", tools)
    client.connect()
    assert len(client.list_tools()) == 1
    result = client.call_tool("search_project_docs", {"query": "mcp"})
    assert result.success
    assert "mcp_request_id" in result.metadata


def test_adapter_registers_unique_id_and_executes() -> None:
    info = MCPToolInfo(
        server_id="demo",
        tool_name="get_project_info",
        description="info",
        permission_level=MCPPermissionLevel.ALLOW,
        input_schema={"type": "object", "properties": {}},
    )
    client = FakeMCPClient("demo", [info])
    client.connect()
    adapter = MCPToolAdapter(info, client)
    assert adapter.name == "mcp.demo.get_project_info"
    result = adapter.execute({})
    assert result.success
    assert result.metadata["server_id"] == "demo"


def test_adapter_ask_permission_deny() -> None:
    info = MCPToolInfo(
        server_id="demo",
        tool_name="create_issue",
        description="write",
        permission_level=MCPPermissionLevel.ASK,
    )
    client = FakeMCPClient("demo", [info])
    client.connect()
    adapter = MCPToolAdapter(
        info,
        client,
        permission_handler=ScriptedPermissionHandler([PermissionDecision.DENY]),
    )
    result = adapter.execute({"title": "x"})
    assert not result.success
    assert result.metadata.get("denied") is True


def test_adapter_deny_dangerous() -> None:
    info = MCPToolInfo(
        server_id="demo",
        tool_name="shell_exec",
        description="danger",
        permission_level=MCPPermissionLevel.DENY,
    )
    client = FakeMCPClient("demo", [info])
    client.connect()
    result = MCPToolAdapter(info, client).execute({"cmd": "rm"})
    assert not result.success


def test_dynamic_register_unregister_collision() -> None:
    registry = ToolRegistry()
    registry.register(CalculatorTool())
    info = MCPToolInfo(
        server_id="demo",
        tool_name="search_project_docs",
        permission_level=MCPPermissionLevel.ALLOW,
    )
    client = FakeMCPClient("demo", [info])
    mgr = MCPManager(configs={"demo": MCPServerConfig(server_id="demo", command="fake")})
    mgr.inject_client("demo", client)
    ids = sync_mcp_tools_to_registry(registry, mgr)
    assert "mcp.demo.search_project_docs" in ids
    assert registry.contains("mcp.demo.search_project_docs")
    assert registry.contains("calculator")
    # replace
    ids2 = sync_mcp_tools_to_registry(registry, mgr)
    assert ids2 == ids
    n = unregister_mcp_tools(registry, server_id="demo")
    assert n == 1
    assert not registry.contains("mcp.demo.search_project_docs")
    assert registry.contains("calculator")


def test_stdio_demo_server_roundtrip(tmp_path: Path) -> None:
    demo = Path(__file__).resolve().parents[1] / "backend" / "app" / "mcp" / "demo_server.py"
    cfg = MCPServerConfig(
        server_id="demo",
        command=sys.executable,
        args=(str(demo),),
        enabled=True,
    )
    client = StdioMCPClient(cfg, workspace_root=str(tmp_path), timeout=15.0)
    client.connect()
    try:
        tools = client.list_tools()
        names = {t.tool_name for t in tools}
        assert "search_project_docs" in names
        assert "get_project_info" in names
        result = client.call_tool("search_project_docs", {"query": "architecture"})
        assert result.success
        assert "doc" in result.content.lower() or "Found" in result.content or "No documentation" in result.content
        info = client.call_tool("get_project_info", {})
        assert info.success
        assert "Project:" in info.content
    finally:
        client.disconnect()


def test_unavailable_server_does_not_raise_on_connect_all(tmp_path: Path) -> None:
    mgr = MCPManager(
        workspace_root=tmp_path,
        configs={
            "broken": MCPServerConfig(
                server_id="broken",
                command="__codewisp_no_such_binary__",
                enabled=True,
            )
        },
    )
    results = mgr.connect_all_enabled()
    assert len(results) == 1
    assert results[0].status.value == "error"
