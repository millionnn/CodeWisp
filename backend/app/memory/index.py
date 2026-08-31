"""SemanticIndex：索引 / 搜索 / 删除 / 重建（上层不知向量细节）。"""

from __future__ import annotations

from pathlib import Path

from backend.app.memory.chunking import (
    chunk_text,
    classify_path,
    content_hash,
    should_index_path,
)
from backend.app.memory.embeddings import EmbeddingProvider, cosine_similarity, default_embedding_provider
from backend.app.memory.models import (
    CodeChunk,
    DocType,
    IndexStats,
    RetrievedContext,
    SemanticDocument,
    new_semantic_chunk_id,
    new_semantic_doc_id,
)
from backend.app.persistence.semantic_repository import SemanticIndexRepository

_MAX_FILE_BYTES = 400_000


class SemanticIndex:
    def __init__(
        self,
        repository: SemanticIndexRepository,
        *,
        embedding: EmbeddingProvider | None = None,
    ) -> None:
        self._repo = repository
        self._embed = embedding or default_embedding_provider()

    @property
    def embedding_model(self) -> str:
        return self._embed.model_name

    def index_workspace(self, workspace: str, *, paths: list[str] | None = None) -> IndexStats:
        """全量或指定路径增量索引。"""
        root = Path(workspace).resolve()
        if not root.is_dir():
            return self._repo.stats(str(root))

        targets = paths
        if targets is None:
            targets = []
            for p in root.rglob("*"):
                if not p.is_file():
                    continue
                rel = p.relative_to(root).as_posix()
                if should_index_path(rel):
                    targets.append(rel)

        for rel in targets:
            self.index_file(str(root), rel)

        self._repo.set_meta(str(root), "embedding_model", self._embed.model_name)
        return self._repo.stats(str(root))

    def index_file(self, workspace: str, path: str) -> bool:
        """索引单个文件；未变化则跳过。返回是否写入。"""
        root = Path(workspace).resolve()
        rel = path.replace("\\", "/").lstrip("./")
        if not should_index_path(rel):
            return False
        full = root / rel
        if not full.is_file():
            self.delete(str(root), rel)
            return True
        try:
            data = full.read_bytes()
        except OSError:
            return False
        if len(data) > _MAX_FILE_BYTES:
            return False
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            return False

        digest = content_hash(text)
        existing = self._repo.get_document(str(root), rel)
        if existing and existing.content_hash == digest:
            return False

        doc_type = DocType(classify_path(rel))
        doc = SemanticDocument(
            document_id=existing.document_id if existing else new_semantic_doc_id(),
            workspace=str(root),
            path=rel,
            doc_type=doc_type,
            content_hash=digest,
            mtime=full.stat().st_mtime,
            size=len(data),
        )
        saved = self._repo.upsert_document(doc)
        # upsert 冲突时 id 可能不同
        doc_id = saved.document_id

        pieces = chunk_text(rel, text)
        try:
            vectors = self._embed.batch_embed([p.content for p in pieces]) if pieces else []
        except Exception:  # noqa: BLE001 — embedding 失败不阻断索引元数据
            vectors = [None] * len(pieces)  # type: ignore[list-item]

        chunks: list[CodeChunk] = []
        for i, piece in enumerate(pieces):
            emb = vectors[i] if i < len(vectors) else None
            chunks.append(
                CodeChunk(
                    chunk_id=new_semantic_chunk_id(),
                    document_id=doc_id,
                    workspace=str(root),
                    path=rel,
                    chunk_index=i,
                    content=piece.content,
                    content_hash=content_hash(piece.content),
                    start_line=piece.start_line,
                    end_line=piece.end_line,
                    symbol=piece.symbol,
                    embedding=emb if isinstance(emb, list) else None,
                    embedding_dim=len(emb) if isinstance(emb, list) else None,
                    embedding_model=self._embed.model_name if isinstance(emb, list) else None,
                )
            )
        self._repo.replace_chunks(doc_id, chunks)
        return True

    def delete(self, workspace: str, path: str) -> None:
        root = str(Path(workspace).resolve())
        self._repo.delete_chunks_for_path(root, path)
        self._repo.delete_document(root, path)

    def rebuild(self, workspace: str) -> IndexStats:
        root = str(Path(workspace).resolve())
        self._repo.clear_workspace(root)
        return self.index_workspace(root)

    def search(
        self,
        workspace: str,
        query: str,
        *,
        top_k: int = 8,
    ) -> list[RetrievedContext]:
        root = str(Path(workspace).resolve())
        q = (query or "").strip()
        if not q:
            return []
        try:
            q_vec = self._embed.embed(q)
        except Exception:  # noqa: BLE001
            q_vec = None

        chunks = self._repo.list_chunks(root)
        scored: list[RetrievedContext] = []
        q_lower = q.lower()
        q_tokens = [t for t in q_lower.replace("/", " ").split() if len(t) > 1]

        for ch in chunks:
            sem = 0.0
            if q_vec is not None and ch.embedding:
                sem = cosine_similarity(q_vec, ch.embedding)
            kw = _keyword_score(q_lower, q_tokens, ch.content.lower(), ch.path.lower())
            path_boost = 0.0
            for tok in q_tokens:
                if tok in ch.path.lower():
                    path_boost += 0.08
                if ch.symbol and tok in ch.symbol.lower():
                    path_boost += 0.1
            score = 0.55 * sem + 0.35 * kw + path_boost
            if score < 0.12:
                continue
            scored.append(
                RetrievedContext(
                    source="code" if not ch.path.lower().endswith(".md") else "documentation",
                    path=ch.path,
                    start_line=ch.start_line,
                    end_line=ch.end_line,
                    score=min(1.0, score),
                    content=ch.content[:2000],
                    provenance={
                        "chunk_id": ch.chunk_id,
                        "symbol": ch.symbol,
                        "embedding_model": ch.embedding_model,
                    },
                )
            )

        scored.sort(key=lambda r: r.score, reverse=True)
        return scored[:top_k]

    def stats(self, workspace: str) -> IndexStats:
        return self._repo.stats(str(Path(workspace).resolve()))


def _keyword_score(q: str, tokens: list[str], content: str, path: str) -> float:
    if not tokens:
        return 0.0
    hits = 0
    for t in tokens:
        if t in content or t in path:
            hits += 1
    base = hits / max(len(tokens), 1)
    if q and q in content:
        base = min(1.0, base + 0.25)
    return base
