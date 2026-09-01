"""LSPService — high-level code intelligence for Agent / API / CLI."""

from __future__ import annotations

from pathlib import Path

from backend.app.lsp.errors import (
    LspError,
    LspOutsideWorkspaceError,
    LspUnavailableError,
    LspUnsupportedLanguageError,
)
from backend.app.lsp.manager import LanguageServerManager, get_default_manager
from backend.app.lsp.models import (
    DefinitionResult,
    Diagnostic,
    HoverResult,
    LspServerStatus,
    LspStatus,
    ReferenceResult,
    Symbol,
)
from backend.app.lsp.policy import LspPolicy, LspPolicyAction
from backend.app.workspace.errors import PathOutsideWorkspaceError, WorkspaceError
from backend.app.workspace.workspace import Workspace


class LSPService:
    """Domain service: detect, diagnostics, definition, references, symbols, hover."""

    def __init__(
        self,
        workspace: Workspace,
        *,
        manager: LanguageServerManager | None = None,
        policy: LspPolicy | None = None,
    ) -> None:
        self._workspace = workspace
        self._manager = manager or get_default_manager()
        self._policy = policy or LspPolicy()

    @property
    def workspace(self) -> Workspace:
        return self._workspace

    def detect(self):
        return self._manager.detect(self._workspace.root)

    def status(self) -> LspStatus:
        detection = self.detect()
        root = str(self._workspace.root.resolve())
        existing = self._manager._clients.get(root)  # noqa: SLF001
        from backend.app.lsp.adapters import UnavailableLanguageServerClient

        if existing is not None and not isinstance(existing, UnavailableLanguageServerClient):
            caps = ["diagnostics", "symbols", "definition", "references", "hover"]
            return LspStatus(
                workspace=root,
                language=getattr(existing, "language", None) or detection.language,
                server=existing.server_name,
                status=LspServerStatus.AVAILABLE,
                message="Language server client ready",
                capabilities=caps,
            )

        caps: list[str] = []
        if detection.status is LspServerStatus.AVAILABLE:
            caps = ["diagnostics", "symbols"]
            if detection.language == "python":
                caps = ["diagnostics", "symbols", "definition", "references", "hover"]
        return LspStatus(
            workspace=str(self._workspace.root),
            language=detection.language,
            server=detection.server,
            status=detection.status,
            message=detection.message,
            capabilities=caps,
        )

    def _validate_path(self, path: str) -> str:
        try:
            resolved = self._workspace.resolve_path(path)
        except PathOutsideWorkspaceError as exc:
            raise LspOutsideWorkspaceError(str(exc)) from exc
        except WorkspaceError as exc:
            raise LspError(str(exc)) from exc
        return self._workspace.relative_to_root(resolved)

    def _client(self):
        return self._manager.get_client(self._workspace.root)

    def _ensure_operation(self, operation: str) -> None:
        decision = self._policy.decide(operation)
        if decision.action is LspPolicyAction.DENY:
            raise LspError(decision.reason)

    def diagnostics(self, path: str | None = None) -> list[Diagnostic]:
        self._ensure_operation("diagnostics")
        status = self.status()
        if status.status is LspServerStatus.UNSUPPORTED:
            raise LspUnsupportedLanguageError(status.message or "Unsupported language")
        if status.status is not LspServerStatus.AVAILABLE:
            raise LspUnavailableError(status.message or "LSP unavailable")

        rel: str | None = None
        if path:
            rel = self._validate_path(path)
        try:
            return self._client().diagnostics(rel)
        except LspError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise LspUnavailableError(str(exc)) from exc

    def definition(self, path: str, line: int, character: int) -> DefinitionResult:
        """line/character are 0-based (LSP convention)."""
        self._ensure_operation("definition")
        rel = self._validate_path(path)
        self._require_available()
        try:
            return self._client().definition(rel, line, character)
        except LspError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise LspUnavailableError(str(exc)) from exc

    def references(self, path: str, line: int, character: int) -> ReferenceResult:
        self._ensure_operation("references")
        rel = self._validate_path(path)
        self._require_available()
        try:
            return self._client().references(rel, line, character)
        except LspError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise LspUnavailableError(str(exc)) from exc

    def symbols(self, path: str) -> list[Symbol]:
        self._ensure_operation("symbols")
        rel = self._validate_path(path)
        self._require_available()
        try:
            return self._client().document_symbols(rel)
        except LspError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise LspUnavailableError(str(exc)) from exc

    def hover(self, path: str, line: int, character: int) -> HoverResult:
        self._ensure_operation("hover")
        rel = self._validate_path(path)
        self._require_available()
        try:
            return self._client().hover(rel, line, character)
        except LspError:
            raise
        except Exception as exc:  # noqa: BLE001
            raise LspUnavailableError(str(exc)) from exc

    def _require_available(self) -> None:
        status = self.status()
        if status.status is LspServerStatus.UNSUPPORTED:
            raise LspUnsupportedLanguageError(status.message or "Unsupported language")
        if status.status is not LspServerStatus.AVAILABLE:
            raise LspUnavailableError(status.message or "LSP unavailable")

    @staticmethod
    def for_workspace_root(
        root: str | Path,
        *,
        manager: LanguageServerManager | None = None,
    ) -> LSPService:
        return LSPService(Workspace(root), manager=manager)
