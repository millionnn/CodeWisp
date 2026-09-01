"""LSP / Code Intelligence domain."""

from backend.app.lsp.errors import (
    LspError,
    LspOutsideWorkspaceError,
    LspTimeoutError,
    LspUnavailableError,
    LspUnsupportedLanguageError,
)
from backend.app.lsp.models import (
    DefinitionResult,
    Diagnostic,
    DiagnosticSeverity,
    HoverResult,
    Location,
    LspServerStatus,
    LspStatus,
    Position,
    Range,
    ReferenceResult,
    Symbol,
    SymbolKind,
)
from backend.app.lsp.service import LSPService

__all__ = [
    "DefinitionResult",
    "Diagnostic",
    "DiagnosticSeverity",
    "HoverResult",
    "LSPService",
    "Location",
    "LspError",
    "LspOutsideWorkspaceError",
    "LspServerStatus",
    "LspStatus",
    "LspTimeoutError",
    "LspUnavailableError",
    "LspUnsupportedLanguageError",
    "Position",
    "Range",
    "ReferenceResult",
    "Symbol",
    "SymbolKind",
]
