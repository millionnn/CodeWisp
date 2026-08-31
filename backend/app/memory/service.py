"""MemoryService：索引、检索、抽取、失效（不进 AgentLoop）。"""

from __future__ import annotations

from pathlib import Path

from backend.app.context.models import MemoryItem
from backend.app.llm.client import LLMClient
from backend.app.memory.embeddings import EmbeddingProvider, default_embedding_provider
from backend.app.memory.extractor import MemoryExtractor
from backend.app.memory.index import SemanticIndex
from backend.app.memory.models import IndexStats, RetrievedContext, TaskRunSummary, new_task_summary_id
from backend.app.memory.retriever import HybridRetriever
from backend.app.persistence.context_repository import ContextRepository
from backend.app.persistence.semantic_repository import SemanticIndexRepository
from backend.app.persistence.store import SqliteStore


class MemoryService:
    def __init__(
        self,
        store: SqliteStore,
        *,
        embedding: EmbeddingProvider | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self._store = store
        self._embed = embedding or default_embedding_provider()
        self._semantic_repo = SemanticIndexRepository(store)
        self._context_repo = ContextRepository(store)
        self._index = SemanticIndex(self._semantic_repo, embedding=self._embed)
        self._retriever = HybridRetriever(
            self._index, semantic_repo=self._semantic_repo, embedding=self._embed
        )
        self._extractor = MemoryExtractor(llm)

    def set_llm(self, llm: LLMClient | None) -> None:
        self._extractor = MemoryExtractor(llm)

    @property
    def index(self) -> SemanticIndex:
        return self._index

    def ensure_index(self, workspace: str) -> IndexStats:
        root = str(Path(workspace).resolve())
        stats = self._index.stats(root)
        if stats.chunks == 0:
            return self._index.index_workspace(root)
        return stats

    def index_workspace(self, workspace: str) -> IndexStats:
        return self._index.index_workspace(str(Path(workspace).resolve()))

    def rebuild_index(self, workspace: str) -> IndexStats:
        return self._index.rebuild(str(Path(workspace).resolve()))

    def index_paths(self, workspace: str, paths: list[str]) -> IndexStats:
        root = str(Path(workspace).resolve())
        self._index.index_workspace(root, paths=paths)
        return self._index.stats(root)

    def search(
        self,
        workspace: str,
        query: str,
        *,
        session_id: str | None = None,
        top_k: int = 10,
    ) -> list[RetrievedContext]:
        root = str(Path(workspace).resolve())
        memories: list[MemoryItem] = []
        if session_id:
            memories = self._context_repo.list_memories(session_id)
        summaries = self._semantic_repo.list_task_summaries(root)
        return self._retriever.retrieve(
            workspace=root,
            query=query,
            memories=memories,
            task_summaries=summaries,
            top_k=top_k,
        )

    def stats(self, workspace: str) -> IndexStats:
        return self._index.stats(str(Path(workspace).resolve()))

    def persist_memories(self, items: list[MemoryItem]) -> list[MemoryItem]:
        saved: list[MemoryItem] = []
        for item in items:
            # 去重
            existing = self._context_repo.list_memories(item.session_id, limit=100)
            if any(e.content.strip().lower() == item.content.strip().lower() for e in existing):
                continue
            saved.append(self._context_repo.save_memory(item))
        return saved

    def extract_after_run(
        self,
        *,
        session_id: str,
        workspace: str,
        objective: str,
        final_answer: str | None,
        observations: list[str],
        changed_files: list[str],
        agent_run_id: str | None = None,
    ) -> list[MemoryItem]:
        result = self._extractor.extract(
            session_id=session_id,
            objective=objective,
            final_answer=final_answer,
            observations=observations,
            changed_files=changed_files,
            source_id=agent_run_id,
            workspace=str(Path(workspace).resolve()),
        )
        return self.persist_memories(result.items)

    def save_task_summary(self, summary: TaskRunSummary) -> TaskRunSummary:
        if not summary.summary_id:
            summary.summary_id = new_task_summary_id()
        try:
            summary.embedding = self._embed.embed(summary.render())
        except Exception:  # noqa: BLE001
            summary.embedding = None
        return self._semantic_repo.save_task_summary(summary)

    def invalidate_paths(self, workspace: str, paths: list[str], *, session_id: str | None = None) -> None:
        root = str(Path(workspace).resolve())
        for path in paths:
            # 重新索引该文件（内容已 revert）
            self._index.index_file(root, path)
        if session_id:
            self._context_repo.invalidate_memories_for_paths(session_id, paths)
