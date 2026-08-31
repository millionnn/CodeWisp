"""LLM Memory Extraction prompts + JSON 解析。"""

from __future__ import annotations

import json
import re
from typing import Any

MEMORY_EXTRACT_SYSTEM = (
    "You extract durable coding-agent memories from a completed task. "
    "Return ONLY valid JSON with key \"memories\" (array). "
    "Each item: type, content, confidence (0-1), files (array of paths). "
    "types: project_fact|architecture_decision|coding_convention|"
    "debugging_insight|task_outcome|verification_knowledge. "
    "Only include high-value reusable knowledge. If none, return {\"memories\":[]}."
)


def build_extract_user_prompt(
    *,
    objective: str,
    final_answer: str | None,
    observations: list[str],
    changed_files: list[str],
) -> str:
    obs = "\n---\n".join(observations[-8:])[:6000]
    files = ", ".join(changed_files[:20]) or "(none)"
    return (
        f"Objective: {objective}\n"
        f"Changed files: {files}\n"
        f"Final answer: {(final_answer or '')[:2000]}\n"
        f"Observations:\n{obs}\n"
    )


def parse_memory_extraction(text: str) -> list[dict[str, Any]]:
    """解析 LLM JSON；非法则返回空列表。"""
    if not text or not text.strip():
        return []
    raw = text.strip()
    # 剥离 markdown fence
    fence = re.search(r"```(?:json)?\s*([\s\S]*?)```", raw)
    if fence:
        raw = fence.group(1).strip()
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        # 尝试截取首个 {...}
        m = re.search(r"\{[\s\S]*\}", raw)
        if not m:
            return []
        try:
            data = json.loads(m.group(0))
        except json.JSONDecodeError:
            return []
    items = data.get("memories") if isinstance(data, dict) else None
    if not isinstance(items, list):
        return []
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        content = item.get("content")
        if not isinstance(content, str) or not content.strip():
            continue
        out.append(item)
    return out
