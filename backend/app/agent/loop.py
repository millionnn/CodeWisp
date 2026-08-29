"""Agent Loop：连接 LLMClient 与 Tool System 的编排核心。

职责：编排（orchestration）。
不负责：HTTP、CLI 展示、具体 Tool 实现、厂商 SDK 细节。
"""

from __future__ import annotations

import json
from typing import Any

from backend.app.agent.errors import AgentError
from backend.app.agent.events import AgentEvent
from backend.app.agent.state import AgentState, AgentStatus
from backend.app.llm.client import LLMClient
from backend.app.llm.errors import CodeWispError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.registry import ToolRegistry
from backend.app.tools.result import ToolResult

DEFAULT_MAX_STEPS = 10

DEFAULT_AGENT_SYSTEM_PROMPT = (
    "你是 CodeWisp，一名编程助手。"
    "请根据当前提供的 tools 完成用户任务："
    "需要外部信息或仓库操作时调用相应工具，并依据工具返回的结果作答；"
    "不要声称使用了未提供的能力，也不要虚构未实际调用的工具结果。"
)


class AgentLoop:
    """最小完整的 Agent 运行时循环。"""

    def __init__(
        self,
        llm: LLMClient,
        executor: ToolExecutor,
        registry: ToolRegistry,
        *,
        max_steps: int = DEFAULT_MAX_STEPS,
        system_prompt: str = DEFAULT_AGENT_SYSTEM_PROMPT,
    ) -> None:
        if max_steps < 1:
            raise AgentError("max_steps 必须 >= 1")
        self.llm = llm
        self.executor = executor
        self.registry = registry
        self.max_steps = max_steps
        self.system_prompt = system_prompt

    def run(
        self,
        task: str,
        *,
        conversation: Conversation | None = None,
    ) -> AgentState:
        """执行一次用户任务，返回最终 AgentState。"""
        text = (task or "").strip()
        if not text:
            state = AgentState(
                status=AgentStatus.FAILED,
                max_steps=self.max_steps,
                conversation=conversation or Conversation(),
                error="任务内容不能为空。",
            )
            return state

        conv = conversation if conversation is not None else Conversation()
        if conversation is None:
            conv.add_system(self.system_prompt)

        state = AgentState(
            status=AgentStatus.RUNNING,
            step=0,
            max_steps=self.max_steps,
            conversation=conv,
        )
        self._emit(state, "agent_started", 0, metadata={"task": text})
        conv.add_user(text)

        tools = self.registry.list_schemas()

        try:
            for step in range(1, self.max_steps + 1):
                state.step = step
                # 调用 LLM 模型
                response = self._call_llm(state, conv, tools)
                # 发送 LLM 调用事件
                self._emit(
                    state,
                    "llm_called",
                    step,
                    metadata={
                        "has_tool_calls": response.has_tool_calls,
                        "finish_reason": response.finish_reason,
                    },
                )
                # 没有 tool_calls：直接返回答案
                if not response.has_tool_calls:
                    answer = response.text
                    conv.add_assistant(answer)
                    state.final_answer = answer
                    state.status = AgentStatus.COMPLETED
                    self._emit(
                        state,
                        "agent_completed",
                        step,
                        metadata={"final_answer": answer},
                    )
                    return state

                # 有 tool_calls：写入 assistant 消息，再逐个执行工具
                state.last_tool_calls = response.tool_calls
                conv.add_assistant_tool_calls(response.content, response.tool_calls)

                for tool_call in response.tool_calls:
                    self._handle_tool_call(state, conv, tool_call, step)

            state.status = AgentStatus.MAX_STEPS
            state.error = f"已达到最大步数 {self.max_steps}，Agent 停止。"
            self._emit(
                state,
                "agent_completed",
                state.step,
                metadata={"status": AgentStatus.MAX_STEPS.value},
            )
            return state

        except CodeWispError as exc:
            state.status = AgentStatus.FAILED
            state.error = str(exc)
            self._emit(
                state,
                "agent_completed",
                state.step,
                metadata={"status": AgentStatus.FAILED.value, "error": str(exc)},
            )
            return state
        except Exception as exc:  # noqa: BLE001 — 边界：不可预期错误 → FAILED
            state.status = AgentStatus.FAILED
            state.error = f"Agent 运行失败：{exc}"
            self._emit(
                state,
                "agent_completed",
                state.step,
                metadata={"status": AgentStatus.FAILED.value, "error": state.error},
            )
            return state

    # 调用 LLM 模型
    def _call_llm(
        self,
        state: AgentState,
        conversation: Conversation,
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        return self.llm.chat(conversation, tools=tools)

    # 执行工具
    def _handle_tool_call(
        self,
        state: AgentState,
        conversation: Conversation,
        tool_call: ToolCall,
        step: int,
    ) -> None:
        self._emit(
            state,
            "tool_called",
            step,
            tool_name=tool_call.name,
            metadata={
                "tool_call_id": tool_call.id,
                "arguments": tool_call.arguments,
                "parse_error": tool_call.parse_error,
            },
        )

        # 工具参数非法：返回错误结果
        if tool_call.parse_error:
            result = ToolResult(
                success=False,
                output=None,
                error=f"工具参数非法：{tool_call.parse_error}",
                metadata={"tool_name": tool_call.name, "tool_call_id": tool_call.id},
            )
        # 工具名称为空：返回错误结果
        elif not (tool_call.name or "").strip():
            result = ToolResult(
                success=False,
                output=None,
                error="工具名称为空。",
                metadata={"tool_call_id": tool_call.id},
            )
        # 工具名称和参数合法：执行工具
        else:
            result = self.executor.execute(tool_call.name, tool_call.arguments)

        event_type = "tool_completed" if result.success else "tool_failed"
        # 发送工具执行事件
        self._emit(
            state,
            event_type,
            step,
            tool_name=tool_call.name,
            metadata=result.to_dict(),
        )

        observation = self._format_observation(result)
        call_id = tool_call.id or f"call_step{step}"
        conversation.add_tool_result(call_id, observation)

    @staticmethod
    def _format_observation(result: ToolResult) -> str:
        """将 ToolResult 转为模型可读的 observation 文本。"""
        return json.dumps(result.to_dict(), ensure_ascii=False)

    # 发送事件，用于记录 Agent 执行过程中的关键事件
    @staticmethod
    def _emit(
        state: AgentState,
        event_type: str,
        step: int,
        *,
        tool_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        state.events.append(
            AgentEvent(
                event_type=event_type,
                step=step,
                tool_name=tool_name,
                metadata=metadata or {},
            )
        )
