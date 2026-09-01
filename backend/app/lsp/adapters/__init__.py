"""Built-in / test language server adapters."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from backend.app.lsp.errors import LspMalformedResponseError, LspTimeoutError, LspUnavailableError
from backend.app.lsp.models import (
    DefinitionResult,
    Diagnostic,
    DiagnosticSeverity,
    HoverResult,
    Location,
    Position,
    Range,
    ReferenceResult,
    Symbol,
    SymbolKind,
)


class UnavailableLanguageServerClient:
    """Graceful no-op client when no server binary is present."""

    def __init__(self, *, language: str, server: str | None, message: str) -> None:
        self._language = language
        self._server = server or "none"
        self._message = message
        self._initialized = False

    @property
    def server_name(self) -> str:
        return self._server

    @property
    def language(self) -> str:
        return self._language

    def initialize(self) -> None:
        self._initialized = True

    def shutdown(self) -> None:
        self._initialized = False

    def diagnostics(self, path: str | None = None) -> list[Diagnostic]:
        raise LspUnavailableError(self._message)

    def definition(self, path: str, line: int, character: int) -> DefinitionResult:
        raise LspUnavailableError(self._message)

    def references(self, path: str, line: int, character: int) -> ReferenceResult:
        raise LspUnavailableError(self._message)

    def document_symbols(self, path: str) -> list[Symbol]:
        raise LspUnavailableError(self._message)

    def hover(self, path: str, line: int, character: int) -> HoverResult:
        raise LspUnavailableError(self._message)


class FakeLanguageServerClient:
    """In-memory client for unit/integration tests (no real LSP process)."""

    def __init__(
        self,
        *,
        language: str = "python",
        server_name: str = "FakeLSP",
        diagnostics: list[Diagnostic] | None = None,
        symbols: dict[str, list[Symbol]] | None = None,
        definitions: dict[tuple[str, int, int], list[Location]] | None = None,
        references: dict[tuple[str, int, int], list[Location]] | None = None,
        hovers: dict[tuple[str, int, int], HoverResult] | None = None,
        fail_with: Exception | None = None,
    ) -> None:
        self._language = language
        self._server_name = server_name
        self._diagnostics = list(diagnostics or [])
        self._symbols = symbols or {}
        self._definitions = definitions or {}
        self._references = references or {}
        self._hovers = hovers or {}
        self._fail_with = fail_with
        self.initialized = False
        self.shutdown_called = False
        self.calls: list[str] = []

    @property
    def server_name(self) -> str:
        return self._server_name

    @property
    def language(self) -> str:
        return self._language

    def initialize(self) -> None:
        self.initialized = True
        self.calls.append("initialize")

    def shutdown(self) -> None:
        self.shutdown_called = True
        self.initialized = False
        self.calls.append("shutdown")

    def _maybe_fail(self) -> None:
        if self._fail_with is not None:
            raise self._fail_with

    def diagnostics(self, path: str | None = None) -> list[Diagnostic]:
        self.calls.append(f"diagnostics:{path or '*'}")
        self._maybe_fail()
        if path is None:
            return list(self._diagnostics)
        return [d for d in self._diagnostics if d.path == path or not d.path]

    def definition(self, path: str, line: int, character: int) -> DefinitionResult:
        self.calls.append(f"definition:{path}:{line}:{character}")
        self._maybe_fail()
        locs = self._definitions.get((path, line, character), [])
        return DefinitionResult(locations=list(locs))

    def references(self, path: str, line: int, character: int) -> ReferenceResult:
        self.calls.append(f"references:{path}:{line}:{character}")
        self._maybe_fail()
        locs = self._references.get((path, line, character), [])
        return ReferenceResult(locations=list(locs))

    def document_symbols(self, path: str) -> list[Symbol]:
        self.calls.append(f"symbols:{path}")
        self._maybe_fail()
        return list(self._symbols.get(path, []))

    def hover(self, path: str, line: int, character: int) -> HoverResult:
        self.calls.append(f"hover:{path}:{line}:{character}")
        self._maybe_fail()
        return self._hovers.get(
            (path, line, character),
            HoverResult(contents=""),
        )


class PyrightCliClient:
    """Python diagnostics via ``pyright --outputjson`` (no auto-install).

    Definition / references / symbols / hover degrade gracefully when the
    full language server protocol is not available — diagnostics remain the
    primary real capability for V1.2.
    """

    DEFAULT_TIMEOUT = 45.0

    def __init__(
        self,
        workspace_root: Path,
        *,
        command: str,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        self._root = Path(workspace_root).resolve()
        self._command = command
        self._timeout = timeout
        self._initialized = False

    @property
    def server_name(self) -> str:
        return "Pyright"

    @property
    def language(self) -> str:
        return "python"

    def initialize(self) -> None:
        self._initialized = True

    def shutdown(self) -> None:
        self._initialized = False

    def diagnostics(self, path: str | None = None) -> list[Diagnostic]:
        args = [self._command, "--outputjson"]
        if path:
            args.append(path)
        try:
            proc = subprocess.run(
                args,
                cwd=str(self._root),
                capture_output=True,
                text=True,
                timeout=self._timeout,
                shell=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise LspTimeoutError(
                f"Pyright timed out after {self._timeout}s"
            ) from exc
        except OSError as exc:
            raise LspUnavailableError(f"Failed to run pyright: {exc}") from exc

        # Pyright exits non-zero when diagnostics exist; still parse stdout.
        raw = (proc.stdout or "").strip()
        if not raw:
            # No JSON → treat as clean or unavailable
            if proc.returncode == 0:
                return []
            stderr = (proc.stderr or "").strip()
            raise LspMalformedResponseError(
                stderr or "Pyright returned empty output"
            )

        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            raise LspMalformedResponseError(
                f"Pyright output is not valid JSON: {exc}"
            ) from exc

        return _parse_pyright_diagnostics(payload, self._root)

    def definition(self, path: str, line: int, character: int) -> DefinitionResult:
        return DefinitionResult(locations=[])

    def references(self, path: str, line: int, character: int) -> ReferenceResult:
        return ReferenceResult(locations=[])

    def document_symbols(self, path: str) -> list[Symbol]:
        """Lightweight AST-based symbols when full LSP is unavailable."""
        return _python_ast_symbols(self._root / path, path)

    def hover(self, path: str, line: int, character: int) -> HoverResult:
        return HoverResult(contents="")


def _parse_pyright_diagnostics(payload: dict, root: Path) -> list[Diagnostic]:
    diags: list[Diagnostic] = []
    for file_entry in payload.get("generalDiagnostics") or []:
        if not isinstance(file_entry, dict):
            continue
        file_path = str(file_entry.get("file") or "")
        try:
            rel = str(Path(file_path).resolve().relative_to(root))
        except Exception:  # noqa: BLE001
            rel = file_path
        rng_raw = file_entry.get("range") or {}
        start = rng_raw.get("start") or {}
        end = rng_raw.get("end") or {}
        severity_raw = str(file_entry.get("severity") or "error").lower()
        try:
            severity = DiagnosticSeverity(severity_raw)
        except ValueError:
            severity = DiagnosticSeverity.ERROR
        code = file_entry.get("rule") or file_entry.get("code")
        diags.append(
            Diagnostic(
                message=str(file_entry.get("message") or ""),
                severity=severity,
                source="pyright",
                range=Range(
                    start=Position(
                        line=int(start.get("line", 0)),
                        character=int(start.get("character", 0)),
                    ),
                    end=Position(
                        line=int(end.get("line", 0)),
                        character=int(end.get("character", 0)),
                    ),
                ),
                code=str(code) if code is not None else None,
                path=rel.replace("\\", "/"),
            )
        )
    return diags


def _python_ast_symbols(abs_path: Path, rel_path: str) -> list[Symbol]:
    import ast

    if not abs_path.is_file():
        return []
    try:
        source = abs_path.read_text(encoding="utf-8")
        tree = ast.parse(source)
    except (OSError, SyntaxError, UnicodeDecodeError):
        return []

    def span(node: ast.AST) -> Range:
        lineno = getattr(node, "lineno", 1) - 1
        end_lineno = getattr(node, "end_lineno", lineno + 1) - 1
        col = getattr(node, "col_offset", 0)
        end_col = getattr(node, "end_col_offset", col)
        return Range(
            start=Position(line=max(0, lineno), character=max(0, col)),
            end=Position(line=max(0, end_lineno), character=max(0, end_col)),
        )

    def walk(nodes: list[ast.AST]) -> list[Symbol]:
        out: list[Symbol] = []
        for node in nodes:
            if isinstance(node, ast.ClassDef):
                children = walk(list(node.body))
                out.append(
                    Symbol(
                        name=node.name,
                        kind=SymbolKind.CLASS,
                        range=span(node),
                        selection_range=span(node),
                        children=children,
                        path=rel_path,
                    )
                )
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append(
                    Symbol(
                        name=node.name,
                        kind=SymbolKind.FUNCTION,
                        range=span(node),
                        selection_range=span(node),
                        path=rel_path,
                    )
                )
        return out

    return walk(list(tree.body))
