"""LanguageServerManager — process/client lifecycle per workspace."""

from __future__ import annotations

from pathlib import Path
from typing import Callable

from backend.app.lsp.adapters import (
    FakeLanguageServerClient,
    PyrightCliClient,
    UnavailableLanguageServerClient,
)
from backend.app.lsp.client import LanguageServerClient
from backend.app.lsp.detector import LanguageDetection, LanguageServerDetector
from backend.app.lsp.models import LspServerStatus


ClientFactory = Callable[[Path, LanguageDetection], LanguageServerClient]


def default_client_factory(root: Path, detection: LanguageDetection) -> LanguageServerClient:
    if detection.status is LspServerStatus.UNSUPPORTED:
        return UnavailableLanguageServerClient(
            language=detection.language or "unknown",
            server=detection.server,
            message=detection.message or "Unsupported language",
        )
    if detection.status is not LspServerStatus.AVAILABLE or not detection.command:
        return UnavailableLanguageServerClient(
            language=detection.language or "unknown",
            server=detection.server,
            message=detection.message or "Language server unavailable",
        )

    language = detection.language or ""
    if language == "python" and detection.command:
        # Prefer pyright CLI path (even if which found pyright-langserver,
        # try sibling `pyright` for --outputjson diagnostics).
        cmd = detection.command
        if cmd.endswith("pyright-langserver"):
            sibling = cmd.replace("pyright-langserver", "pyright")
            if Path(sibling).exists():
                cmd = sibling
            else:
                # langserver alone — still attempt `pyright` on PATH later;
                # fall back to unavailable for diagnostics-heavy path.
                from shutil import which

                alt = which("pyright")
                if alt:
                    cmd = alt
                else:
                    return UnavailableLanguageServerClient(
                        language="python",
                        server="Pyright",
                        message=(
                            "Found pyright-langserver but not `pyright` CLI. "
                            "Install pyright for diagnostics support."
                        ),
                    )
        return PyrightCliClient(root, command=cmd)

    # Other languages: detected but no full adapter yet
    return UnavailableLanguageServerClient(
        language=language or "unknown",
        server=detection.server,
        message=(
            f"Language '{language}' detected and server binary found, "
            f"but a full adapter is not implemented in V1.2. "
            f"Python/Pyright is the primary supported path."
        ),
    )


class LanguageServerManager:
    """Reuse one client per workspace root within the process."""

    def __init__(
        self,
        *,
        client_factory: ClientFactory | None = None,
    ) -> None:
        self._factory = client_factory or default_client_factory
        self._clients: dict[str, LanguageServerClient] = {}
        self._detections: dict[str, LanguageDetection] = {}

    def detect(self, workspace_root: str | Path) -> LanguageDetection:
        root = str(Path(workspace_root).expanduser().resolve())
        if root not in self._detections:
            self._detections[root] = LanguageServerDetector.detect(root)
        return self._detections[root]

    def get_client(self, workspace_root: str | Path) -> LanguageServerClient:
        root_path = Path(workspace_root).expanduser().resolve()
        key = str(root_path)
        existing = self._clients.get(key)
        if existing is not None:
            return existing

        detection = self.detect(root_path)
        client = self._factory(root_path, detection)
        try:
            client.initialize()
        except Exception:  # noqa: BLE001 — degrade to unavailable
            client = UnavailableLanguageServerClient(
                language=detection.language or "unknown",
                server=detection.server,
                message=f"Language server failed to initialize: {detection.message}",
            )
            client.initialize()
        self._clients[key] = client
        return client

    def inject_client(self, workspace_root: str | Path, client: LanguageServerClient) -> None:
        """Test helper: force a specific client for a workspace."""
        key = str(Path(workspace_root).expanduser().resolve())
        try:
            client.initialize()
        except Exception:  # noqa: BLE001
            pass
        self._clients[key] = client

    def shutdown(self, workspace_root: str | Path | None = None) -> None:
        if workspace_root is None:
            for client in list(self._clients.values()):
                try:
                    client.shutdown()
                except Exception:  # noqa: BLE001
                    pass
            self._clients.clear()
            return
        key = str(Path(workspace_root).expanduser().resolve())
        client = self._clients.pop(key, None)
        if client is not None:
            try:
                client.shutdown()
            except Exception:  # noqa: BLE001
                pass

    def clear_detection_cache(self) -> None:
        self._detections.clear()


# Process-wide default manager (sessions reuse within one CodeWisp process)
_DEFAULT_MANAGER: LanguageServerManager | None = None


def get_default_manager() -> LanguageServerManager:
    global _DEFAULT_MANAGER
    if _DEFAULT_MANAGER is None:
        _DEFAULT_MANAGER = LanguageServerManager()
    return _DEFAULT_MANAGER
