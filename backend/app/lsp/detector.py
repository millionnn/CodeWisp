"""Language / Language-Server detection for a workspace."""

from __future__ import annotations

import shutil
from dataclasses import dataclass
from pathlib import Path

from backend.app.lsp.models import LspServerStatus


@dataclass(frozen=True)
class LanguageDetection:
    language: str | None
    server: str | None
    status: LspServerStatus
    message: str = ""
    command: str | None = None

    def to_dict(self) -> dict:
        return {
            "language": self.language,
            "server": self.server,
            "status": self.status.value,
            "message": self.message,
            "command": self.command,
        }


# Extension → language id
_EXT_LANGUAGE: dict[str, str] = {
    ".py": "python",
    ".pyi": "python",
    ".ts": "typescript",
    ".tsx": "typescript",
    ".js": "javascript",
    ".jsx": "javascript",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".java": "java",
    ".rs": "rust",
}

# Preferred server binaries per language (first found wins)
_SERVER_CANDIDATES: dict[str, list[tuple[str, str]]] = {
    # (display_name, executable)
    "python": [("Pyright", "pyright"), ("Pyright", "pyright-langserver")],
    "typescript": [("typescript-language-server", "typescript-language-server")],
    "javascript": [("typescript-language-server", "typescript-language-server")],
    "java": [("jdtls", "jdtls")],
    "rust": [("rust-analyzer", "rust-analyzer")],
}


class LanguageServerDetector:
    """Detect primary language and whether a suitable server binary exists."""

    @staticmethod
    def detect(workspace_root: str | Path) -> LanguageDetection:
        root = Path(workspace_root).expanduser().resolve()
        language = LanguageServerDetector.detect_language(root)
        if language is None:
            return LanguageDetection(
                language=None,
                server=None,
                status=LspServerStatus.UNSUPPORTED,
                message="No supported source files found in workspace.",
            )

        for display, exe in _SERVER_CANDIDATES.get(language, []):
            found = shutil.which(exe)
            if found:
                return LanguageDetection(
                    language=language,
                    server=display,
                    status=LspServerStatus.AVAILABLE,
                    message=f"Found {exe} at {found}",
                    command=found,
                )

        return LanguageDetection(
            language=language,
            server=_SERVER_CANDIDATES.get(language, [(None, None)])[0][0],
            status=LspServerStatus.UNAVAILABLE,
            message=(
                f"Language '{language}' detected, but no language server binary "
                f"found on PATH. Install and configure it locally; CodeWisp will "
                f"not download or install servers."
            ),
            command=None,
        )

    @staticmethod
    def detect_language(workspace_root: Path) -> str | None:
        """Pick dominant language by counting supported source files."""
        counts: dict[str, int] = {}
        skip = {
            ".git",
            ".venv",
            "venv",
            "node_modules",
            "__pycache__",
            ".pytest_cache",
            "dist",
            "build",
            ".tox",
            ".mypy_cache",
            ".ruff_cache",
        }
        try:
            for path in workspace_root.rglob("*"):
                if not path.is_file():
                    continue
                if any(part in skip for part in path.parts):
                    continue
                lang = _EXT_LANGUAGE.get(path.suffix.lower())
                if lang:
                    counts[lang] = counts.get(lang, 0) + 1
                    # Early exit for large trees once we have a clear winner
                    if counts[lang] >= 50:
                        break
        except OSError:
            return None

        if not counts:
            return None
        return max(counts.items(), key=lambda kv: kv[1])[0]

    @staticmethod
    def language_for_path(path: str | Path) -> str | None:
        return _EXT_LANGUAGE.get(Path(path).suffix.lower())
