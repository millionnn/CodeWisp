"""MCPManager — server lifecycle; AgentLoop never manages MCP processes."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from backend.app.mcp.client import FakeMCPClient, MCPClient, StdioMCPClient
from backend.app.mcp.config import load_mcp_configs
from backend.app.mcp.errors import (
    MCPError,
    MCPInvalidConfigurationError,
    MCPServerNotFoundError,
    MCPServerUnavailableError,
)
from backend.app.mcp.models import (
    MCPServerConfig,
    MCPServerRuntime,
    MCPServerStatus,
    MCPToolInfo,
)

ClientFactory = Callable[[MCPServerConfig, str | None], MCPClient]


def default_client_factory(
    config: MCPServerConfig, workspace_root: str | None
) -> MCPClient:
    return StdioMCPClient(config, workspace_root=workspace_root)


class MCPManager:
    """Lifecycle + discovery for configured MCP servers (allowlist from config)."""

    def __init__(
        self,
        *,
        workspace_root: str | Path | None = None,
        client_factory: ClientFactory | None = None,
        configs: dict[str, MCPServerConfig] | None = None,
    ) -> None:
        self._workspace_root = (
            str(Path(workspace_root).expanduser().resolve())
            if workspace_root is not None
            else None
        )
        self._factory = client_factory or default_client_factory
        self._configs: dict[str, MCPServerConfig] = dict(configs or {})
        self._clients: dict[str, MCPClient] = {}
        self._runtimes: dict[str, MCPServerRuntime] = {}
        if configs is None and self._workspace_root is not None:
            self.reload_config()
        else:
            for cfg in self._configs.values():
                self._runtimes[cfg.server_id] = MCPServerRuntime(config=cfg)

    @property
    def workspace_root(self) -> str | None:
        return self._workspace_root

    def reload_config(self) -> dict[str, MCPServerConfig]:
        """Reload filesystem configs; disconnect removed servers."""
        try:
            loaded = load_mcp_configs(workspace_root=self._workspace_root)
        except MCPInvalidConfigurationError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise MCPInvalidConfigurationError(str(exc)) from exc

        removed = set(self._configs) - set(loaded)
        for sid in removed:
            self.disconnect(sid)
            self._runtimes.pop(sid, None)
            self._clients.pop(sid, None)

        self._configs = loaded
        for sid, cfg in loaded.items():
            existing = self._runtimes.get(sid)
            if existing is None:
                status = (
                    MCPServerStatus.DISABLED
                    if not cfg.enabled
                    else MCPServerStatus.CONFIGURED
                )
                self._runtimes[sid] = MCPServerRuntime(config=cfg, status=status)
            else:
                was_connected = existing.connected
                existing.config = cfg
                if not cfg.enabled:
                    if was_connected:
                        self.disconnect(sid)
                    existing.status = MCPServerStatus.DISABLED
                    existing.tools = []
                elif not was_connected:
                    existing.status = MCPServerStatus.CONFIGURED
        return dict(self._configs)

    def list_servers(self) -> list[MCPServerRuntime]:
        return [self._runtimes[k] for k in sorted(self._runtimes)]

    def get_server(self, server_id: str) -> MCPServerRuntime:
        sid = (server_id or "").strip()
        runtime = self._runtimes.get(sid)
        if runtime is None:
            raise MCPServerNotFoundError(f"MCP server not found: {sid}")
        return runtime

    def inject_client(self, server_id: str, client: MCPClient) -> None:
        """Test helper: register a fake client under an allowlisted id."""
        sid = server_id.strip()
        if sid not in self._configs:
            # Allow injecting config-less fakes in tests by synthesizing config
            self._configs[sid] = MCPServerConfig(
                server_id=sid, command="fake", enabled=True
            )
        self._clients[sid] = client
        runtime = self._runtimes.get(sid)
        if runtime is None:
            runtime = MCPServerRuntime(config=self._configs[sid])
            self._runtimes[sid] = runtime
        if not client.connected:
            try:
                client.connect()
            except MCPError as exc:
                runtime.status = MCPServerStatus.ERROR
                runtime.message = str(exc)
                return
        try:
            tools = client.list_tools()
        except MCPError as exc:
            runtime.status = MCPServerStatus.ERROR
            runtime.message = str(exc)
            tools = []
        runtime.status = MCPServerStatus.CONNECTED
        runtime.message = ""
        runtime.tools = tools

    def connect(self, server_id: str) -> MCPServerRuntime:
        runtime = self.get_server(server_id)
        if not runtime.config.enabled:
            runtime.status = MCPServerStatus.DISABLED
            raise MCPServerUnavailableError(
                f"MCP server '{server_id}' is disabled"
            )
        runtime.status = MCPServerStatus.CONNECTING
        runtime.message = ""
        client = self._clients.get(server_id)
        if client is None:
            client = self._factory(runtime.config, self._workspace_root)
            self._clients[server_id] = client
        try:
            if not client.connected:
                client.connect()
            tools = client.list_tools()
        except MCPError as exc:
            runtime.status = MCPServerStatus.ERROR
            runtime.message = str(exc)
            runtime.tools = []
            raise
        except Exception as exc:  # noqa: BLE001
            runtime.status = MCPServerStatus.ERROR
            runtime.message = str(exc)
            runtime.tools = []
            raise MCPServerUnavailableError(str(exc)) from exc

        runtime.status = MCPServerStatus.CONNECTED
        runtime.tools = tools
        runtime.message = ""
        if isinstance(client, StdioMCPClient):
            runtime.protocol_version = client.protocol_version
        return runtime

    def disconnect(self, server_id: str) -> MCPServerRuntime:
        runtime = self.get_server(server_id)
        client = self._clients.pop(server_id, None)
        if client is not None:
            try:
                client.disconnect()
            except Exception:  # noqa: BLE001
                pass
        runtime.status = (
            MCPServerStatus.DISABLED
            if not runtime.config.enabled
            else MCPServerStatus.DISCONNECTED
        )
        runtime.tools = []
        runtime.message = ""
        return runtime

    def restart(self, server_id: str) -> MCPServerRuntime:
        try:
            self.disconnect(server_id)
        except MCPServerNotFoundError:
            raise
        except Exception:  # noqa: BLE001
            pass
        return self.connect(server_id)

    def connect_all_enabled(self) -> list[MCPServerRuntime]:
        results: list[MCPServerRuntime] = []
        for sid, cfg in sorted(self._configs.items()):
            if not cfg.enabled:
                rt = self._runtimes.get(sid)
                if rt:
                    rt.status = MCPServerStatus.DISABLED
                    results.append(rt)
                continue
            try:
                results.append(self.connect(sid))
            except MCPError as exc:
                rt = self._runtimes[sid]
                rt.status = MCPServerStatus.ERROR
                rt.message = str(exc)
                results.append(rt)
        return results

    def list_all_tools(self) -> list[MCPToolInfo]:
        tools: list[MCPToolInfo] = []
        for rt in self.list_servers():
            if rt.connected:
                tools.extend(rt.tools)
        return tools

    def get_client(self, server_id: str) -> MCPClient:
        client = self._clients.get(server_id)
        if client is None or not client.connected:
            raise MCPServerUnavailableError(
                f"MCP server '{server_id}' is not connected"
            )
        return client

    def shutdown(self) -> None:
        for sid in list(self._clients):
            try:
                self.disconnect(sid)
            except Exception:  # noqa: BLE001
                pass


# Process-wide managers keyed by workspace (session isolation of connections)
_MANAGERS: dict[str, MCPManager] = {}


def get_manager_for_workspace(workspace_root: str | Path) -> MCPManager:
    key = str(Path(workspace_root).expanduser().resolve())
    mgr = _MANAGERS.get(key)
    if mgr is None:
        mgr = MCPManager(workspace_root=key)
        _MANAGERS[key] = mgr
    return mgr


def reset_managers_for_tests() -> None:
    for mgr in list(_MANAGERS.values()):
        mgr.shutdown()
    _MANAGERS.clear()
