"""Planner LLM prompts。"""

from __future__ import annotations

PLAN_SYSTEM = (
    "You are a coding-task planner for CodeWisp. "
    "Output ONLY valid JSON for a structured plan. "
    "Schema: {\"objective\": str, \"steps\": [{\"index\": int, \"title\": str, "
    "\"description\": str, \"status\": \"pending|in_progress\", "
    "\"relevant_files\": [str], \"verification\": str, \"rationale\": str, "
    "\"dependencies\": [int]}]}. "
    "Rules: steps MUST be sequential starting at index 0 (or 1). "
    "The first step status MUST be in_progress; all later steps MUST be pending. "
    "Do not mark any step completed/failed/skipped in the initial plan. "
    "Do not modify files. Do not invent tools. Keep 3-8 concrete steps."
)

REPLAN_SYSTEM = (
    "You update an existing coding plan after new observations. "
    "Output ONLY valid JSON with the same schema as planning. "
    "Keep the SAME number of steps and the SAME titles whenever possible. "
    "Only change step status: pending / in_progress / completed / skipped. "
    "Do not replace the whole plan with a single step. "
    "Do not invent new failed steps. "
    "Do not modify the workspace."
)


def build_plan_user_prompt(
    *,
    goal: str,
    project_rules: str,
    retrieved: str,
    memories: str,
) -> str:
    return (
        f"Task goal:\n{goal}\n\n"
        f"Project rules:\n{project_rules or '(none)'}\n\n"
        f"Relevant retrieval:\n{retrieved or '(none)'}\n\n"
        f"Memories:\n{memories or '(none)'}\n"
    )


def build_replan_user_prompt(
    *,
    goal: str,
    current_plan_json: str,
    observation: str,
    memories: str,
    retrieved: str,
) -> str:
    return (
        f"Goal:\n{goal}\n\n"
        f"Current plan JSON:\n{current_plan_json}\n\n"
        f"New observation:\n{observation[:4000]}\n\n"
        f"Memories:\n{memories or '(none)'}\n\n"
        f"Retrieval:\n{retrieved or '(none)'}\n"
    )
