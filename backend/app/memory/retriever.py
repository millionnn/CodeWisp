"""Hybrid Retrieval：keyword + semantic + ranking。"""

from __future__ import annotations

from backend.app.context.models import MemoryItem
from backend.app.memory.embeddings import EmbeddingProvider, cosine_similarity, default_embedding_provider
from backend.app.memory.index import SemanticIndex
from backend.app.memory.models import RetrievedContext, TaskRunSummary
from backend.app.persistence.semantic_repository import SemanticIndexRepository


class HybridRetriever:
    def __init__(
        self,
        index: SemanticIndex,
        *,
        semantic_repo: SemanticIndexRepository | None = None,
        embedding: EmbeddingProvider | None = None,
    ) -> None:
        self._index = index
        self._repo = semantic_repo
        self._embed = embedding or default_embedding_provider()

    def retrieve(
        self,
        *,
        workspace: str,
        query: str,
        memories: list[MemoryItem] | None = None,
        task_summaries: list[TaskRunSummary] | None = None,
        top_k: int = 10,
    ) -> list[RetrievedContext]:
        results: list[RetrievedContext] = []
        results.extend(self._index.search(workspace, query, top_k=top_k))

        q_vec = None
        try:
            q_vec = self._embed.embed(query)
        except Exception:  # noqa: BLE001
            pass

        for mem in memories or []:
            if mem.invalidated:
                continue
            score = _text_overlap_score(query, mem.content)
            conf = 0.5
            # confidence from extended field if present
            conf_attr = getattr(mem, "confidence", None)
            if isinstance(conf_attr, (int, float)):
                conf = float(conf_attr)
            score = min(1.0, score * 0.7 + conf * 0.3 + 0.05)
            if score < 0.15:
                continue
            results.append(
                RetrievedContext(
                    source="memory",
                    path=mem.file_path,
                    start_line=mem.line_start,
                    end_line=mem.line_end,
                    score=score,
                    content=mem.content,
                    provenance={
                        "memory_id": mem.memory_id,
                        "source_type": mem.source_type.value,
                        "source_id": mem.source_id,
                        "category": mem.category.value,
                    },
                )
            )

        for summary in task_summaries or []:
            text = summary.render()
            score = _text_overlap_score(query, text)
            if q_vec and summary.embedding:
                score = max(score, cosine_similarity(q_vec, summary.embedding))
            if score < 0.12:
                continue
            results.append(
                RetrievedContext(
                    source="task_summary",
                    path=None,
                    start_line=None,
                    end_line=None,
                    score=min(1.0, score + 0.05),
                    content=text,
                    provenance={
                        "summary_id": summary.summary_id,
                        "agent_run_id": summary.agent_run_id,
                        "session_id": summary.session_id,
                    },
                )
            )

        # 去重：同 path+start_line 或同 content 前缀
        results = _dedupe_rank(results)
        return results[:top_k]


def _text_overlap_score(query: str, text: str) -> float:
    q = query.lower()
    t = text.lower()
    tokens = [x for x in q.replace("/", " ").split() if len(x) > 1]
    if not tokens:
        return 0.0
    hits = sum(1 for tok in tokens if tok in t)
    score = hits / len(tokens)
    if q in t:
        score = min(1.0, score + 0.3)
    return score


def _dedupe_rank(items: list[RetrievedContext]) -> list[RetrievedContext]:
    items = sorted(items, key=lambda r: r.score, reverse=True)
    seen: set[str] = set()
    out: list[RetrievedContext] = []
    for item in items:
        key = f"{item.source}:{item.path}:{item.start_line}:{item.content[:80]}"
        if key in seen:
            continue
        seen.add(key)
        out.append(item)
    return out
