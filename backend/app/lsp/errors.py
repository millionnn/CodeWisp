"""LSP domain errors — structured, never crash the Agent."""

from __future__ import annotations


class LspError(Exception):
    """LSP domain base error."""


class LspUnavailableError(LspError):
    """Language server not available / failed to start."""


class LspUnsupportedLanguageError(LspError):
    """Workspace language not supported."""


class LspTimeoutError(LspError):
    """Language server request timed out."""


class LspOutsideWorkspaceError(LspError):
    """Requested path is outside the session workspace."""


class LspMalformedResponseError(LspError):
    """Language server returned unusable payload."""
