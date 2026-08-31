"""ContextBudget：基于模型 context_window 的启发式 token 预算。"""

#计算器：我的agent模型窗口有多大，还剩多少token
#目前不引入tokenizer
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

from backend.app.llm.messages import Conversation, Message

EstimatorType = Literal["heuristic_chars"]

# 无 context_window 时的保守 fallback
DEFAULT_CONTEXT_WINDOW = 32_000
DEFAULT_RESERVED_OUTPUT = 4_096
DEFAULT_SAFETY_BUFFER = 1_024

# ~4 chars / token（英文偏乐观；中文偏保守，整体够用）
CHARS_PER_TOKEN = 4.0


@dataclass(frozen=True)
class ContextBudget:
    """一次模型请求可用的上下文预算。"""

    context_limit: int
    reserved_output_tokens: int
    safety_buffer: int
    estimator: EstimatorType = "heuristic_chars"

    @classmethod
    def from_context_window(
        cls,
        context_window: int | None,
        *,
        reserved_output_tokens: int = DEFAULT_RESERVED_OUTPUT,
        safety_buffer: int = DEFAULT_SAFETY_BUFFER,
    ) -> ContextBudget:
        limit = context_window if context_window and context_window > 0 else DEFAULT_CONTEXT_WINDOW
        return cls(
            context_limit=limit,
            reserved_output_tokens=max(0, reserved_output_tokens),
            safety_buffer=max(0, safety_buffer),
        )

    @property
    def usable_budget(self) -> int:
        return max(0, self.context_limit - self.reserved_output_tokens - self.safety_buffer)

    def estimate(self, text: str | None) -> int:
        if not text:
            return 0
        return max(1, int(len(text) / CHARS_PER_TOKEN)) if text else 0

    def estimate_message(self, message: Message) -> int:
        n = self.estimate(message.content or "")
        for tc in message.tool_calls:
            n += self.estimate(tc.name)
            raw = tc.arguments_raw
            if raw is None:
                raw = str(tc.arguments)
            n += self.estimate(raw)
        if message.tool_call_id:
            n += self.estimate(message.tool_call_id)
        # role / 结构开销
        return n + 4

    def estimate_conversation(self, conversation: Conversation) -> int:
        return sum(self.estimate_message(m) for m in conversation.messages)

    def estimate_tools(self, tools: list[dict[str, Any]] | None) -> int:
        if not tools:
            return 0
        # schema JSON 粗估
        total = 0
        for t in tools:
            total += self.estimate(str(t))
        return total

    def remaining(self, used: int) -> int:
        return max(0, self.usable_budget - max(0, used))

    def fits(self, used: int, *, extra: int = 0) -> bool:
        return (used + max(0, extra)) <= self.usable_budget

    def to_dict(self) -> dict[str, Any]:
        return {
            "context_limit": self.context_limit,
            "reserved_output_tokens": self.reserved_output_tokens,
            "safety_buffer": self.safety_buffer,
            "usable_budget": self.usable_budget,
            "estimator": self.estimator,
        }
