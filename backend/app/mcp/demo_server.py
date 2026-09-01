#!/usr/bin/env python3
"""codewisp-demo-mcp — offline stdio MCP server for V1.3 demos/tests.

Tools:
  search_project_docs — search bundled/project docs by keyword
  get_project_info    — return basic project metadata

Speaks MCP JSON-RPC over stdio with Content-Length framing.
No third-party accounts required.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Bundled fallback docs (offline-friendly)
_BUNDLED_DOCS: list[dict[str, str]] = [
    {
        "path": "docs/architecture.md",
        "title": "Architecture",
        "text": (
            "CodeWisp Agent Runtime uses AgentLoop → ToolRegistry → Tools. "
            "MCP is a Tool Extension Layer via MCPToolAdapter. "
            "Git and LSP remain native domains."
        ),
    },
    {
        "path": "docs/v1.3-mcp-report.md",
        "title": "MCP Integration",
        "text": (
            "V1.3 adds MCP client, dynamic tool discovery, permission integration, "
            "and graceful degradation when servers are unavailable."
        ),
    },
    {
        "path": "README.md",
        "title": "README",
        "text": (
            "CodeWisp is a from-scratch coding agent runtime with CLI and FastAPI. "
            "Use /mcp servers and /mcp tools to inspect MCP capabilities."
        ),
    },
    {
        "path": "docs/bug-notes.md",
        "title": "Bug notes",
        "text": (
            "Common bugs: off-by-one in plan steps; permission ASK for write tools; "
            "MCP failures must not crash AgentLoop."
        ),
    },
]


def _read_frame() -> dict | None:
    headers: dict[str, str] = {}
    stdin = sys.stdin.buffer
    while True:
        line = stdin.readline()
        if line == b"":
            return None
        if line in (b"\r\n", b"\n"):
            break
        text = line.decode("ascii", errors="replace").rstrip("\r\n")
        if ":" in text:
            k, v = text.split(":", 1)
            headers[k.strip().lower()] = v.strip()
    length = int(headers.get("content-length") or "0")
    if length <= 0:
        return None
    body = stdin.read(length)
    return json.loads(body.decode("utf-8"))


def _write_msg(msg: dict) -> None:
    body = json.dumps(msg, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    header = f"Content-Length: {len(body)}\r\n\r\n".encode("ascii")
    sys.stdout.buffer.write(header + body)
    sys.stdout.buffer.flush()


def _ok(req_id: object, result: object) -> None:
    _write_msg({"jsonrpc": "2.0", "id": req_id, "result": result})


def _err(req_id: object, code: int, message: str) -> None:
    _write_msg(
        {
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": code, "message": message},
        }
    )


def _workspace_docs() -> list[dict[str, str]]:
    root = Path(os.environ.get("CODEWISP_WORKSPACE") or os.getcwd())
    docs: list[dict[str, str]] = []
    for rel in ("docs", "."):
        base = root / rel if rel != "." else root
        if not base.is_dir():
            continue
        for path in sorted(base.rglob("*.md")):
            try:
                if path.stat().st_size > 200_000:
                    continue
                text = path.read_text(encoding="utf-8", errors="replace")
            except OSError:
                continue
            try:
                rel_path = str(path.relative_to(root))
            except ValueError:
                rel_path = str(path)
            docs.append(
                {
                    "path": rel_path,
                    "title": path.stem,
                    "text": text[:4000],
                }
            )
            if len(docs) >= 40:
                return docs
    return docs or list(_BUNDLED_DOCS)


def _tool_search(arguments: dict) -> dict:
    query = str(arguments.get("query") or arguments.get("q") or "").strip().lower()
    if not query:
        return {
            "content": [{"type": "text", "text": "query is required"}],
            "isError": True,
        }
    docs = _workspace_docs()
    hits: list[str] = []
    for doc in docs:
        blob = f"{doc['path']} {doc['title']} {doc['text']}".lower()
        if query in blob or any(tok in blob for tok in query.split() if len(tok) > 2):
            snippet = doc["text"].replace("\n", " ")
            if len(snippet) > 220:
                snippet = snippet[:219] + "…"
            hits.append(f"- {doc['path']}: {snippet}")
    if not hits:
        text = f"No documentation matches for '{query}'."
    else:
        text = f"Found {len(hits)} doc(s) for '{query}':\n" + "\n".join(hits[:8])
    return {"content": [{"type": "text", "text": text}], "isError": False}


def _tool_info(_arguments: dict) -> dict:
    root = Path(os.environ.get("CODEWISP_WORKSPACE") or os.getcwd())
    name = root.name
    has_py = (root / "pyproject.toml").is_file() or (root / "setup.py").is_file()
    has_git = (root / ".git").is_dir()
    text = (
        f"Project: {name}\n"
        f"Root: {root}\n"
        f"Python project: {'yes' if has_py else 'no'}\n"
        f"Git repo: {'yes' if has_git else 'no'}\n"
        f"MCP demo server: codewisp-demo-mcp\n"
        f"Tools: search_project_docs, get_project_info"
    )
    return {"content": [{"type": "text", "text": text}], "isError": False}


TOOLS = [
    {
        "name": "search_project_docs",
        "description": (
            "Search project documentation relevant to a bug or topic. "
            "Use when the user asks to find docs or project knowledge."
        ),
        "inputSchema": {
            "type": "object",
            "properties": {
                "query": {
                    "type": "string",
                    "description": "Search keywords",
                }
            },
            "required": ["query"],
        },
        "annotations": {"readOnlyHint": True},
    },
    {
        "name": "get_project_info",
        "description": "Return basic project metadata (name, root, python/git flags).",
        "inputSchema": {
            "type": "object",
            "properties": {},
        },
        "annotations": {"readOnlyHint": True},
    },
]


def main() -> int:
    while True:
        msg = _read_frame()
        if msg is None:
            break
        method = msg.get("method")
        req_id = msg.get("id")
        params = msg.get("params") or {}

        if method == "initialize":
            _ok(
                req_id,
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "codewisp-demo-mcp", "version": "1.3"},
                },
            )
        elif method == "notifications/initialized":
            continue
        elif method == "tools/list":
            _ok(req_id, {"tools": TOOLS})
        elif method == "tools/call":
            name = str(params.get("name") or "")
            args = params.get("arguments") or {}
            if not isinstance(args, dict):
                args = {}
            if name == "search_project_docs":
                _ok(req_id, _tool_search(args))
            elif name == "get_project_info":
                _ok(req_id, _tool_info(args))
            else:
                _err(req_id, -32601, f"Unknown tool: {name}")
        elif method == "ping":
            _ok(req_id, {})
        elif req_id is not None:
            _err(req_id, -32601, f"Method not found: {method}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
