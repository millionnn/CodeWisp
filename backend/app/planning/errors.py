"""Planning 错误。"""


class PlanningError(Exception):
    """Planner 领域错误。"""


class PlanParseError(PlanningError):
    """LLM Plan JSON 无法解析。"""
