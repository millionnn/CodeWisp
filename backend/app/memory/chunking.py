"""语言无关、结构感知的代码/文档分块。"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class TextChunk:
    content: str
    start_line: int
    end_line: int
    symbol: str | None = None


# 扩展名 → 文档类型提示
SOURCE_EXTS = {
    ".py",
    ".js",
    ".jsx",
    ".ts",
    ".tsx",
    ".java",
    ".go",
    ".rs",
    ".rb",
    ".php",
    ".c",
    ".cc",
    ".cpp",
    ".h",
    ".hpp",
    ".cs",
    ".kt",
    ".swift",
    ".scala",
}
DOC_EXTS = {".md", ".rst", ".txt"}
CONFIG_EXTS = {".json", ".yaml", ".yml", ".toml", ".ini", ".cfg"}
RULE_NAMES = {"AGENTS.md", "CLAUDE.md", "README.md", "README"}


def classify_path(path: str) -> str:
    name = Path(path).name
    if name in RULE_NAMES or name.upper() in {"AGENTS.MD", "CLAUDE.MD"}:
        return "project_rule"
    ext = Path(path).suffix.lower()
    if ext in DOC_EXTS:
        return "documentation"
    if ext in CONFIG_EXTS:
        return "config"
    if ext in SOURCE_EXTS:
        return "source"
    return "source"


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def chunk_text(path: str, text: str, *, max_lines: int = 80) -> list[TextChunk]:
    """按路径选择结构感知策略；失败则行窗口。"""
    if not text.strip():
        return []
    ext = Path(path).suffix.lower()
    name = Path(path).name.lower()
    try:
        if ext == ".py":
            chunks = _chunk_by_patterns(
                text,
                [
                    re.compile(r"^(class\s+\w+.*)$", re.M),
                    re.compile(r"^(def\s+\w+.*)$", re.M),
                    re.compile(r"^(async\s+def\s+\w+.*)$", re.M),
                ],
            )
            if chunks:
                return chunks
        if ext in {".js", ".jsx", ".ts", ".tsx"}:
            chunks = _chunk_by_patterns(
                text,
                [
                    re.compile(r"^(export\s+)?(async\s+)?function\s+\w+", re.M),
                    re.compile(r"^(export\s+)?class\s+\w+", re.M),
                    re.compile(r"^(export\s+)?const\s+\w+\s*=\s*(async\s*)?\(", re.M),
                ],
            )
            if chunks:
                return chunks
        if ext == ".java":
            chunks = _chunk_by_patterns(
                text,
                [
                    re.compile(r"^(public\s+|private\s+|protected\s+)?(class|interface|enum)\s+\w+", re.M),
                    re.compile(
                        r"^(public\s+|private\s+|protected\s+|static\s+|final\s+)*\w+[\w<>\[\]]*\s+\w+\s*\([^;]*\)\s*\{?",
                        re.M,
                    ),
                ],
            )
            if chunks:
                return chunks
        if ext in DOC_EXTS or name in {"agents.md", "claude.md", "readme.md"}:
            chunks = _chunk_markdown(text)
            if chunks:
                return chunks
        if ext in CONFIG_EXTS:
            chunks = _chunk_line_windows(text, window=40, overlap=5)
            if chunks:
                return chunks
    except Exception:  # noqa: BLE001 — 任意解析失败 → fallback
        pass
    return _chunk_line_windows(text, window=max_lines, overlap=10)


def _chunk_markdown(text: str) -> list[TextChunk]:
    lines = text.splitlines()
    headers = [i for i, ln in enumerate(lines) if re.match(r"^#{1,3}\s+", ln)]
    if not headers:
        return _chunk_line_windows(text, window=60, overlap=8)
    headers.append(len(lines))
    out: list[TextChunk] = []
    for i in range(len(headers) - 1):
        start = headers[i]
        end = headers[i + 1]
        body = "\n".join(lines[start:end]).strip()
        if not body:
            continue
        symbol = lines[start].lstrip("#").strip()[:80]
        out.append(TextChunk(body, start + 1, end, symbol=symbol or None))
    return out


def _chunk_by_patterns(text: str, patterns: list[re.Pattern[str]]) -> list[TextChunk]:
    lines = text.splitlines()
    starts: list[tuple[int, str]] = []
    for i, ln in enumerate(lines):
        for pat in patterns:
            if pat.match(ln):
                starts.append((i, ln.strip()[:80]))
                break
    if len(starts) < 1:
        return []
    starts.append((len(lines), ""))
    out: list[TextChunk] = []
    for i in range(len(starts) - 1):
        s, symbol = starts[i]
        e = starts[i + 1][0]
        # 合并过小块
        body = "\n".join(lines[s:e]).strip()
        if not body:
            continue
        if e - s > 120:
            # 过大：再按行切
            sub = _chunk_line_windows("\n".join(lines[s:e]), window=80, overlap=10, line_offset=s)
            out.extend(sub)
        else:
            out.append(TextChunk(body, s + 1, e, symbol=symbol or None))
    return out


def _chunk_line_windows(
    text: str,
    *,
    window: int,
    overlap: int,
    line_offset: int = 0,
) -> list[TextChunk]:
    lines = text.splitlines()
    if not lines:
        return []
    out: list[TextChunk] = []
    step = max(1, window - overlap)
    i = 0
    idx = 0
    while i < len(lines):
        chunk_lines = lines[i : i + window]
        body = "\n".join(chunk_lines).strip()
        if body:
            start = line_offset + i + 1
            end = line_offset + i + len(chunk_lines)
            out.append(TextChunk(body, start, end, symbol=None))
            idx += 1
        if i + window >= len(lines):
            break
        i += step
    return out


def should_index_path(path: str) -> bool:
    """过滤明显不该索引的路径。"""
    parts = path.replace("\\", "/").split("/")
    skip_dirs = {
        ".git",
        "node_modules",
        "__pycache__",
        ".venv",
        "venv",
        "dist",
        "build",
        ".tox",
        ".mypy_cache",
        ".pytest_cache",
    }
    if any(p in skip_dirs for p in parts):
        return False
    name = Path(path).name
    if name.startswith(".") and name not in {".env.example"}:
        # 仍允许 AGENTS 等
        if name.upper() not in {"AGENTS.MD", "CLAUDE.MD"}:
            return False
    ext = Path(path).suffix.lower()
    if ext in SOURCE_EXTS | DOC_EXTS | CONFIG_EXTS:
        return True
    if name in RULE_NAMES:
        return True
    return False
