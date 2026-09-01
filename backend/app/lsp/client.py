"""LanguageServerClient protocol and shared helpers."""

from __future__ import annotations

from typing import Protocol, runtime_checkable

from backend.app.lsp.models import (
    DefinitionResult,
    Diagnostic,
    HoverResult,
    ReferenceResult,
    Symbol,
)


@runtime_checkable
class LanguageServerClient(Protocol):
    """Sync facade over a language server (AgentLoop is synchronous)."""

    @property
    def server_name(self) -> str: ...

    @property
    def language(self) -> str: ...

    def initialize(self) -> None: ...

    def shutdown(self) -> None: ...

    def diagnostics(self, path: str | None = None) -> list[Diagnostic]: ...

    def definition(
        self, path: str, line: int, character: int
    ) -> DefinitionResult: ...

    def references(
        self, path: str, line: int, character: int
    ) -> ReferenceResult: ...

    def document_symbols(self, path: str) -> list[Symbol]: ...

    def hover(self, path: str, line: int, character: int) -> HoverResult: ...
