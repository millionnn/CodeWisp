"""LSP domain models — structured, independent of JSON-RPC payloads."""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class DiagnosticSeverity(str, Enum):
    ERROR = "error"
    WARNING = "warning"
    INFORMATION = "information"
    HINT = "hint"

    @classmethod
    def from_lsp_int(cls, value: int | None) -> DiagnosticSeverity:
        mapping = {
            1: cls.ERROR,
            2: cls.WARNING,
            3: cls.INFORMATION,
            4: cls.HINT,
        }
        return mapping.get(int(value or 1), cls.ERROR)


class SymbolKind(str, Enum):
    FILE = "file"
    MODULE = "module"
    NAMESPACE = "namespace"
    PACKAGE = "package"
    CLASS = "class"
    METHOD = "method"
    PROPERTY = "property"
    FIELD = "field"
    CONSTRUCTOR = "constructor"
    ENUM = "enum"
    INTERFACE = "interface"
    FUNCTION = "function"
    VARIABLE = "variable"
    CONSTANT = "constant"
    STRING = "string"
    NUMBER = "number"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    KEY = "key"
    NULL = "null"
    ENUM_MEMBER = "enum_member"
    STRUCT = "struct"
    EVENT = "event"
    OPERATOR = "operator"
    TYPE_PARAMETER = "type_parameter"
    UNKNOWN = "unknown"

    @classmethod
    def from_lsp_int(cls, value: int | None) -> SymbolKind:
        # LSP SymbolKind enum (1-26)
        names = [
            "file",
            "module",
            "namespace",
            "package",
            "class",
            "method",
            "property",
            "field",
            "constructor",
            "enum",
            "interface",
            "function",
            "variable",
            "constant",
            "string",
            "number",
            "boolean",
            "array",
            "object",
            "key",
            "null",
            "enum_member",
            "struct",
            "event",
            "operator",
            "type_parameter",
        ]
        idx = int(value or 0) - 1
        if 0 <= idx < len(names):
            return cls(names[idx])
        return cls.UNKNOWN


class LspServerStatus(str, Enum):
    AVAILABLE = "available"
    UNAVAILABLE = "unavailable"
    UNSUPPORTED = "unsupported"
    ERROR = "error"


@dataclass(frozen=True)
class Position:
    """0-based line/character (LSP convention)."""

    line: int
    character: int

    def to_dict(self) -> dict[str, Any]:
        return {"line": self.line, "character": self.character}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Position:
        data = data or {}
        return cls(line=int(data.get("line", 0)), character=int(data.get("character", 0)))

    def display_1based(self) -> str:
        return f"{self.line + 1}:{self.character + 1}"


@dataclass(frozen=True)
class Range:
    start: Position
    end: Position

    def to_dict(self) -> dict[str, Any]:
        return {"start": self.start.to_dict(), "end": self.end.to_dict()}

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> Range:
        data = data or {}
        return cls(
            start=Position.from_dict(data.get("start")),
            end=Position.from_dict(data.get("end")),
        )


@dataclass(frozen=True)
class Diagnostic:
    message: str
    severity: DiagnosticSeverity = DiagnosticSeverity.ERROR
    source: str = ""
    range: Range | None = None
    code: str | None = None
    path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "message": self.message,
            "severity": self.severity.value,
            "source": self.source,
            "range": self.range.to_dict() if self.range else None,
            "code": self.code,
            "path": self.path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Diagnostic:
        sev = data.get("severity", "error")
        if isinstance(sev, int):
            severity = DiagnosticSeverity.from_lsp_int(sev)
        else:
            try:
                severity = DiagnosticSeverity(str(sev).lower())
            except ValueError:
                severity = DiagnosticSeverity.ERROR
        rng = data.get("range")
        return cls(
            message=str(data.get("message") or ""),
            severity=severity,
            source=str(data.get("source") or ""),
            range=Range.from_dict(rng) if isinstance(rng, dict) else None,
            code=str(data["code"]) if data.get("code") is not None else None,
            path=str(data.get("path") or ""),
        )

    def render_line(self) -> str:
        loc = self.range.start.display_1based() if self.range else "?"
        mark = {
            DiagnosticSeverity.ERROR: "✗",
            DiagnosticSeverity.WARNING: "⚠",
            DiagnosticSeverity.INFORMATION: "ℹ",
            DiagnosticSeverity.HINT: "·",
        }.get(self.severity, "·")
        return f"{mark} Line {loc}  {self.message}"


@dataclass(frozen=True)
class Location:
    path: str
    range: Range
    uri: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "uri": self.uri,
            "range": self.range.to_dict(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Location:
        return cls(
            path=str(data.get("path") or ""),
            uri=str(data.get("uri") or ""),
            range=Range.from_dict(data.get("range")),
        )

    def render_line(self) -> str:
        start = self.range.start.display_1based()
        return f"{self.path}:{start}"


@dataclass
class Symbol:
    name: str
    kind: SymbolKind
    range: Range
    selection_range: Range | None = None
    children: list[Symbol] = field(default_factory=list)
    path: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "kind": self.kind.value,
            "range": self.range.to_dict(),
            "selection_range": (
                self.selection_range.to_dict() if self.selection_range else None
            ),
            "children": [c.to_dict() for c in self.children],
            "path": self.path,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> Symbol:
        kind_raw = data.get("kind", "unknown")
        if isinstance(kind_raw, int):
            kind = SymbolKind.from_lsp_int(kind_raw)
        else:
            try:
                kind = SymbolKind(str(kind_raw))
            except ValueError:
                kind = SymbolKind.UNKNOWN
        sel = data.get("selection_range")
        children_raw = data.get("children") or []
        return cls(
            name=str(data.get("name") or ""),
            kind=kind,
            range=Range.from_dict(data.get("range")),
            selection_range=Range.from_dict(sel) if isinstance(sel, dict) else None,
            children=[cls.from_dict(c) for c in children_raw if isinstance(c, dict)],
            path=str(data.get("path") or ""),
        )

    def render_tree(self, indent: int = 0) -> list[str]:
        prefix = "  " * indent + ("├── " if indent else "")
        suffix = "()" if self.kind in {SymbolKind.FUNCTION, SymbolKind.METHOD} else ""
        lines = [f"{prefix}{self.name}{suffix}"]
        for child in self.children:
            lines.extend(child.render_tree(indent + 1))
        return lines


@dataclass(frozen=True)
class DefinitionResult:
    locations: list[Location] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"locations": [loc.to_dict() for loc in self.locations]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> DefinitionResult:
        locs = data.get("locations") or []
        return cls(locations=[Location.from_dict(x) for x in locs if isinstance(x, dict)])


@dataclass(frozen=True)
class ReferenceResult:
    locations: list[Location] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {"locations": [loc.to_dict() for loc in self.locations]}

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReferenceResult:
        locs = data.get("locations") or []
        return cls(locations=[Location.from_dict(x) for x in locs if isinstance(x, dict)])


@dataclass(frozen=True)
class HoverResult:
    contents: str
    range: Range | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "contents": self.contents,
            "range": self.range.to_dict() if self.range else None,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> HoverResult:
        rng = data.get("range")
        return cls(
            contents=str(data.get("contents") or ""),
            range=Range.from_dict(rng) if isinstance(rng, dict) else None,
        )


@dataclass
class LspStatus:
    workspace: str
    language: str | None
    server: str | None
    status: LspServerStatus
    message: str = ""
    capabilities: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace": self.workspace,
            "language": self.language,
            "server": self.server,
            "status": self.status.value,
            "message": self.message,
            "capabilities": list(self.capabilities),
            "available": self.status is LspServerStatus.AVAILABLE,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> LspStatus:
        try:
            status = LspServerStatus(str(data.get("status") or "unavailable"))
        except ValueError:
            status = LspServerStatus.UNAVAILABLE
        return cls(
            workspace=str(data.get("workspace") or ""),
            language=data.get("language"),
            server=data.get("server"),
            status=status,
            message=str(data.get("message") or ""),
            capabilities=list(data.get("capabilities") or []),
        )

    def render(self) -> str:
        mark = {
            LspServerStatus.AVAILABLE: "✓ available",
            LspServerStatus.UNAVAILABLE: "✗ unavailable",
            LspServerStatus.UNSUPPORTED: "○ unsupported",
            LspServerStatus.ERROR: "✗ error",
        }.get(self.status, self.status.value)
        lines = [
            "Code Intelligence",
            f"Workspace : {self.workspace}",
            f"Language  : {self.language or '-'}",
            f"Server    : {self.server or '-'}",
            f"Status    : {mark}",
        ]
        if self.message:
            lines.append(f"Note      : {self.message}")
        return "\n".join(lines)
