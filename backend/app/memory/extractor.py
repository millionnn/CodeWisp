"""Memory 抽取：LLM 结构化 + 启发式 fallback；失败不抛到主循环。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from backend.app.context.memory import MemoryCandidateExtractor
from backend.app.context.models import MemoryCategory, MemoryItem, MemorySourceType
from backend.app.context.priority import ContextPriority
from backend.app.llm.client import LLMClient
from backend.app.llm.messages import Conversation
from backend.app.memory.models import MemoryType
from backend.app.memory.prompts import (
    MEMORY_EXTRACT_SYSTEM,
    build_extract_user_prompt,
    parse_memory_extraction,
)

_TYPE_TO_CATEGORY = {
    MemoryType.PROJECT_FACT.value: MemoryCategory.IMPORTANT_FACT,
    MemoryType.ARCHITECTURE_DECISION.value: MemoryCategory.ARCHITECTURE,
    MemoryType.CODING_CONVENTION.value: MemoryCategory.CONSTRAINT,
    MemoryType.DEBUGGING_INSIGHT.value: MemoryCategory.IMPORTANT_FACT,
    MemoryType.TASK_OUTCOME.value: MemoryCategory.WORKFLOW,
    MemoryType.VERIFICATION_KNOWLEDGE.value: MemoryCategory.WORKFLOW,
}


@dataclass
class ExtractionResult:
    items: list[MemoryItem]
    used_llm: bool
    error: str | None = None


class MemoryExtractor:
    def __init__(self, llm: LLMClient | None = None) -> None:
        self._llm = llm
        self._heuristic = MemoryCandidateExtractor()

    def extract(
        self,
        *,
        session_id: str,
        objective: str,
        final_answer: str | None,
        observations: list[str],
        changed_files: list[str],
        source_id: str | None = None,
        workspace: str | None = None,
    ) -> ExtractionResult:
        items: list[MemoryItem] = []
        used_llm = False
        error: str | None = None

        if self._llm is not None:
            try:
                conv = Conversation()
                conv.add_system(MEMORY_EXTRACT_SYSTEM)
                conv.add_user(
                    build_extract_user_prompt(
                        objective=objective,
                        final_answer=final_answer,
                        observations=observations,
                        changed_files=changed_files,
                    )
                )
                resp = self._llm.chat(conv, tools=None)
                used_llm = True
                for raw in parse_memory_extraction(resp.text):
                    item = _item_from_llm(
                        session_id=session_id,
                        raw=raw,
                        source_id=source_id,
                        workspace=workspace,
                    )
                    if item:
                        items.append(item)
            except Exception as exc:  # noqa: BLE001
                error = str(exc)

        if not items:
            # heuristic fallback
            blob = "\n".join(
                [objective, final_answer or "", *observations[-5:], *changed_files]
            )
            for cand in self._heuristic.extract_from_agent(blob, source_id=source_id):
                items.append(
                    MemoryItem.create(
                        session_id=session_id,
                        category=cand.category,
                        content=cand.content,
                        source_type=cand.source_type,
                        source_id=cand.source_id or source_id,
                        file_path=cand.file_path
                        or (changed_files[0] if changed_files else None),
                        priority=ContextPriority.P1,
                    )
                )

        # Decimal convention 等确定性增强
        joined = "\n".join(observations + [final_answer or "", objective]).lower()
        if "decimal" in joined and ("float" in joined or "money" in joined or "金额" in joined):
            items.append(
                MemoryItem.create(
                    session_id=session_id,
                    category=MemoryCategory.CONSTRAINT,
                    content="Use Decimal for monetary calculations, not float.",
                    source_type=MemorySourceType.TOOL_OBSERVATION,
                    source_id=source_id,
                    file_path=changed_files[0] if changed_files else None,
                    priority=ContextPriority.P1,
                )
            )

        return ExtractionResult(items=_dedupe(items), used_llm=used_llm, error=error)


def _item_from_llm(
    *,
    session_id: str,
    raw: dict[str, Any],
    source_id: str | None,
    workspace: str | None,
) -> MemoryItem | None:
    content = str(raw.get("content") or "").strip()
    if not content:
        return None
    mtype = str(raw.get("type") or MemoryType.PROJECT_FACT.value)
    category = _TYPE_TO_CATEGORY.get(mtype, MemoryCategory.IMPORTANT_FACT)
    files = raw.get("files") or []
    path = files[0] if isinstance(files, list) and files else None
    conf = raw.get("confidence")
    try:
        confidence = float(conf) if conf is not None else 0.7
    except (TypeError, ValueError):
        confidence = 0.7
    if confidence < 0.4:
        return None
    item = MemoryItem.create(
        session_id=session_id,
        category=category,
        content=content[:800],
        source_type=MemorySourceType.AGENT,
        source_id=source_id,
        file_path=str(path) if path else None,
        priority=ContextPriority.P1,
    )
    # 动态附加字段（V1.0+）
    object.__setattr__  # placate linters
    item.__dict__["memory_type"] = mtype  # type: ignore[attr-defined]
    item.__dict__["confidence"] = confidence  # type: ignore[attr-defined]
    item.__dict__["workspace"] = workspace  # type: ignore[attr-defined]
    item.__dict__["embedding_status"] = "pending"  # type: ignore[attr-defined]
    return item


def _dedupe(items: list[MemoryItem]) -> list[MemoryItem]:
    seen: set[str] = set()
    out: list[MemoryItem] = []
    for it in items:
        key = it.content.strip().lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(it)
    return out
