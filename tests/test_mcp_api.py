"""MCP API route tests."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.app.api.app import create_app
from backend.app.api.deps import build_app_state
from backend.app.mcp.client import FakeMCPClient
from backend.app.mcp.manager import MCPManager, reset_managers_for_tests
from backend.app.mcp.models import MCPPermissionLevel, MCPServerConfig, MCPToolInfo
from backend.app.permissions.broker import PendingPermissionBroker
from backend.app.permissions.handler import AlwaysAllowPermissionHandler


@pytest.fixture(autouse=True)
def _reset() -> None:
    reset_managers_for_tests()
    yield
    reset_managers_for_tests()


def test_mcp_api_connect_and_list(tmp_path: Path) -> None:
    state = build_app_state(db_path=tmp_path / "api.db")
    # Override permission for tool call tests
    state.agents._permission_handler = AlwaysAllowPermissionHandler()

    session = state.sessions.create_session(
        title="mcp",
        workspace=tmp_path,
    )
    info = MCPToolInfo(
        server_id="demo",
        tool_name="get_project_info",
        permission_level=MCPPermissionLevel.ALLOW,
    )
    mgr = MCPManager(
        workspace_root=session.workspace,
        configs={"demo": MCPServerConfig(server_id="demo", command="fake")},
    )
    mgr.inject_client("demo", FakeMCPClient("demo", [info]))
    state.agents._mcp_managers[session.workspace] = mgr

    app = create_app(state=state)
    client = TestClient(app)
    r = client.get(f"/api/sessions/{session.session_id}/mcp/servers")
    assert r.status_code == 200
    body = r.json()
    assert body["servers"][0]["server_id"] == "demo"
    assert body["servers"][0]["connected"] is True

    r2 = client.get(f"/api/sessions/{session.session_id}/mcp/servers/demo/tools")
    assert r2.status_code == 200
    assert r2.json()["tools"][0]["tool_name"] == "get_project_info"

    r3 = client.post(
        f"/api/sessions/{session.session_id}/mcp/servers/demo/tools/get_project_info/call",
        json={"arguments": {}, "confirm": True},
    )
    assert r3.status_code == 200
    assert r3.json()["success"] is True
