"""轻量 Memory 候选抽取：规则/启发式；失败不影响 ContextManager。"""

from __future__ import annotations

import re
from dataclasses import dataclass

from backend.app.context.models import MemoryCategory, MemoryItem, MemorySourceType
from backend.app.context.priority import ContextPriority

#启发式规则：这句话像不像决策？像不像约束

_DECISION_RE = re.compile(
    r"(?:决定|decision|we (?:will|should)|采用|选用|选择)\s*[:：]?\s*(.+)",
    re.IGNORECASE,
)
_CONSTRAINT_RE = re.compile(
    r"(?:约束|constraint|must not|不得|禁止|不要)\s*[:：]?\s*(.+)",
    re.IGNORECASE,
)
_ARCH_RE = re.compile(
    r"(?:架构|architecture|位于|bug (?:is )?in|模块)\s*[:：]?\s*(.+)",
    re.IGNORECASE,
)
_FACT_RE = re.compile(
    r"(?:重要|important|发现|found that|note that)\s*[:：]?\s*(.+)",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class MemoryCandidate:
    category: MemoryCategory
    content: str
    source_type: MemorySourceType
    source_id: str | None = None
    file_path: str | None = None
    line_start: int | None = None
    line_end: int | None = None
    priority: ContextPriority = ContextPriority.P1


class MemoryCandidateExtractor:
    """从 user / agent / tool 文本中抽取 Memory 候选。"""

    def extract_from_user(self, text: str, *, source_id: str | None = None) -> list[MemoryCandidate]:
        return self._scan(text, MemorySourceType.USER, source_id=source_id)

    def extract_from_agent(self, text: str, *, source_id: str | None = None) -> list[MemoryCandidate]:
        if not text:
            return []
        return self._scan(text, MemorySourceType.AGENT, source_id=source_id)

    def extract_from_tool(
        self,
        text: str,
        *,
        source_id: str | None = None,
        file_path: str | None = None,
    ) -> list[MemoryCandidate]:
        if not text:
            return []
        # 工具结果通常嘈杂：只取较短且像事实的片段
        candidates = self._scan(
            text[:2000],
            MemorySourceType.TOOL_OBSERVATION,
            source_id=source_id,
            file_path=file_path,
        )
        return candidates[:3]

    def _scan(
        self,
        text: str,
        source_type: MemorySourceType,
        *,
        source_id: str | None,
        file_path: str | None = None,
    ) -> list[MemoryCandidate]:
        out: list[MemoryCandidate] = []
        for line in text.splitlines():
            line = line.strip()
            if len(line) < 8 or len(line) > 400:
                continue
            matched = (
                (_DECISION_RE, MemoryCategory.DECISION),
                (_CONSTRAINT_RE, MemoryCategory.CONSTRAINT),
                (_ARCH_RE, MemoryCategory.ARCHITECTURE),
                (_FACT_RE, MemoryCategory.IMPORTANT_FACT),
            )
            for pattern, category in matched:
                m = pattern.search(line)
                if not m:
                    continue
                content = (m.group(1) if m.lastindex else line).strip()
                if not content:
                    content = line
                out.append(
                    MemoryCandidate(
                        category=category,
                        content=content[:500],
                        source_type=source_type,
                        source_id=source_id,
                        file_path=file_path,
                    )
                )
                break
        return out[:5]


def candidates_to_items(
    session_id: str,
    candidates: list[MemoryCandidate],
) -> list[MemoryItem]:
    return [
        MemoryItem.create(
            session_id=session_id,
            category=c.category,
            content=c.content,
            source_type=c.source_type,
            source_id=c.source_id,
            file_path=c.file_path,
            line_start=c.line_start,
            line_end=c.line_end,
            priority=c.priority,
        )
        for c in candidates
    ]
