"""Semantic Memory 领域模型与检索结果。"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from backend.app.session.ids import new_id


def new_semantic_doc_id() -> str:
    return new_id("sdoc")


def new_semantic_chunk_id() -> str:
    return new_id("schunk")


def new_task_summary_id() -> str:
    return new_id("tsum")


def new_memory_source_id() -> str:
    return new_id("msrc")


class MemoryType(str, Enum):
    PROJECT_FACT = "project_fact"
    ARCHITECTURE_DECISION = "architecture_decision"
    CODING_CONVENTION = "coding_convention"
    DEBUGGING_INSIGHT = "debugging_insight"
    TASK_OUTCOME = "task_outcome"
    VERIFICATION_KNOWLEDGE = "verification_knowledge"


class EmbeddingStatus(str, Enum):
    PENDING = "pending"
    READY = "ready"
    FAILED = "failed"
    INVALIDATED = "invalidated"


class DocType(str, Enum):
    SOURCE = "source"
    DOCUMENTATION = "documentation"
    PROJECT_RULE = "project_rule"
    CONFIG = "config"
    MEMORY = "memory"
    TASK_SUMMARY = "task_summary"


@dataclass(frozen=True)
class RetrievedContext:
    """检索结果：供 ContextManager 决定是否注入。"""

    source: str  # code | memory | task_summary | documentation
    path: str | None
    start_line: int | None
    end_line: int | None
    score: float
    content: str
    provenance: dict[str, Any] = field(default_factory=dict)

    def render(self) -> str:
        loc = self.path or "(memory)"
        if self.start_line is not None:
            loc += f":{self.start_line}"
            if self.end_line is not None:
                loc += f"-{self.end_line}"
        return f"[{self.source} score={self.score:.3f}] {loc}\n{self.content.strip()}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "path": self.path,
            "start_line": self.start_line,
            "end_line": self.end_line,
            "score": self.score,
            "content": self.content,
            "provenance": dict(self.provenance),
        }


@dataclass
class CodeChunk:
    chunk_id: str
    document_id: str
    workspace: str
    path: str
    chunk_index: int
    content: str
    content_hash: str
    start_line: int | None = None
    end_line: int | None = None
    symbol: str | None = None
    embedding: list[float] | None = None
    embedding_dim: int | None = None
    embedding_model: str | None = None


@dataclass
class SemanticDocument:
    document_id: str
    workspace: str
    path: str
    doc_type: DocType
    content_hash: str
    mtime: float | None = None
    size: int | None = None
    indexed_at: str | None = None


@dataclass
class IndexStats:
    workspace: str
    documents: int = 0
    chunks: int = 0
    memories: int = 0
    task_summaries: int = 0
    embedding_model: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace": self.workspace,
            "documents": self.documents,
            "chunks": self.chunks,
            "memories": self.memories,
            "task_summaries": self.task_summaries,
            "embedding_model": self.embedding_model,
        }


@dataclass
class TaskRunSummary:
    summary_id: str
    session_id: str
    workspace: str
    objective: str
    agent_run_id: str | None = None
    changed_files: list[str] = field(default_factory=list)
    important_decisions: list[str] = field(default_factory=list)
    tests: list[str] = field(default_factory=list)
    failures: list[str] = field(default_factory=list)
    final_result: str = ""
    unresolved_issues: list[str] = field(default_factory=list)
    embedding: list[float] | None = None
    created_at: str | None = None

    def to_summary_json(self) -> dict[str, Any]:
        return {
            "objective": self.objective,
            "changed_files": list(self.changed_files),
            "important_decisions": list(self.important_decisions),
            "tests": list(self.tests),
            "failures": list(self.failures),
            "final_result": self.final_result,
            "unresolved_issues": list(self.unresolved_issues),
        }

    def render(self) -> str:
        lines = [
            f"Objective: {self.objective}",
            f"Result: {self.final_result}",
        ]
        if self.changed_files:
            lines.append("Files: " + ", ".join(self.changed_files[:12]))
        if self.important_decisions:
            lines.append("Decisions: " + "; ".join(self.important_decisions[:6]))
        if self.failures:
            lines.append("Failures: " + "; ".join(self.failures[:4]))
        return "\n".join(lines)
