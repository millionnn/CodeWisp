"""Agent Loop：连接 LLMClient 与 Tool System 的编排核心。

职责：编排（orchestration）。
不负责：HTTP、CLI 展示、具体 Tool 实现、厂商 SDK 细节。

V0.5：在现有多轮 Tool Calling 上增加有限预算语义、termination_reason、
以及 permission_required 硬停——不写死任何语言/测试修复策略。
"""

from __future__ import annotations

import json
from typing import Any

from backend.app.agent.errors import AgentError
from backend.app.agent.event_sink import AgentEventSink, NullEventSink
from backend.app.agent.events import AgentEvent
from backend.app.agent.state import AgentState, AgentStatus
from backend.app.context.manager import ContextManager
from backend.app.llm.client import LLMClient
from backend.app.llm.errors import CodeWispError
from backend.app.llm.messages import Conversation
from backend.app.llm.response import LLMResponse, ToolCall
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.registry import ToolRegistry
from backend.app.tools.result import ToolResult

# 迭代预算：每次 LLM 调用计 1 step（含修复闭环所需的多轮工具）
DEFAULT_MAX_STEPS = 40

DEFAULT_AGENT_SYSTEM_PROMPT = (
    "你是 CodeWisp，一名编程助手。"
    "请根据当前提供的 tools 完成用户任务："
    "需要外部信息或仓库操作时调用相应工具，并依据工具返回的结果（Observation）决定下一步——"
    "可以继续调用工具，或在任务已完成后给出最终回答。"
    "若上下文中有 Plan：严格逐步执行——"
    "只做当前标记为 [>] / in_progress 的那一步；"
    "在该步内依次调用所需工具（可多个）；"
    "该步目标达成后调用一次 complete_plan_step 发信号，再开始下一步；"
    "每轮 LLM 回复最多调用一次 complete_plan_step，禁止在同一轮连跳多步；"
    "不要在未调用 complete_plan_step 的情况下跳步，也不要在 Plan 未全部逐步完成前给出最终回答。"
    "若你修改了代码或配置，应通过合适的检查或命令验证结果；验证已通过则停止，不要无意义地重复同一操作。"
    "若工具返回 permission_required（尚无交互授权通道），请停止自动继续并说明原因。"
    "若工具返回用户拒绝执行（user_denied / DENY），请根据 Observation 调整计划或向用户说明，"
    "不要尝试绕过权限策略。"
    "不要用 python/perl 等解释器去绕过被拒绝或需授权的命令（例如不要用 os.remove 代替 rm）。"
    "删除文件应使用 run_command 的 rm，并等待用户授权；不要寻找变通执行路径。"
    "不要声称使用了未提供的能力，也不要虚构未实际调用的工具结果。"
    "可用步数有限，请高效完成任务。"
)

_PLAN_CONTINUE_NUDGE = (
    "【系统】Plan 尚未逐步完成。请只执行当前 [>] 步骤："
    "调用该步所需工具，完成后调用 complete_plan_step，再进入下一步。"
    "全部步骤完成后才能给出最终回答。"
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
        event_sink: AgentEventSink | None = None,
        context_manager: ContextManager | None = None,
    ) -> None:
        if max_steps < 1:
            raise AgentError("max_steps 必须 >= 1")
        self.llm = llm
        self.executor = executor
        self.registry = registry
        self.max_steps = max_steps
        self.system_prompt = system_prompt
        self._event_sink: AgentEventSink = event_sink or NullEventSink()
        self.context_manager = context_manager

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
                termination_reason="failed",
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
        self._emit_event(state, "agent_started", 0, metadata={"task": text})
        conv.add_user(text)
        if self.context_manager is not None:
            self.context_manager.update_after_user(text)

        tools = self.registry.list_schemas()

        try:
            for step in range(1, self.max_steps + 1):
                state.step = step
                if self.context_manager is not None and hasattr(
                    self.context_manager, "begin_agent_turn"
                ):
                    self.context_manager.begin_agent_turn()
                self._emit_event(
                    state,
                    "llm_started",
                    step,
                    metadata={"model_id": getattr(self.llm.config, "model", None)},
                )
                response = self._call_llm(state, conv, tools)
                self._emit_event(
                    state,
                    "llm_called",
                    step,
                    metadata={
                        "has_tool_calls": response.has_tool_calls,
                        "finish_reason": response.finish_reason,
                    },
                )

                if not response.has_tool_calls:
                    answer = response.text
                    if (
                        self.context_manager is not None
                        and hasattr(self.context_manager, "plan_has_open_steps")
                        and self.context_manager.plan_has_open_steps()
                    ):
                        conv.add_assistant(answer or "（试图提前结束）")
                        conv.add_user(_PLAN_CONTINUE_NUDGE)
                        continue
                    conv.add_assistant(answer)
                    if self.context_manager is not None:
                        self.context_manager.update_after_assistant(answer)
                    state.final_answer = answer
                    state.status = AgentStatus.COMPLETED
                    state.termination_reason = "completed"
                    self._emit_event(
                        state,
                        "agent_completed",
                        step,
                        metadata={
                            "final_answer": answer,
                            "termination_reason": state.termination_reason,
                            "status": state.status.value,
                        },
                    )
                    return state

                state.last_tool_calls = response.tool_calls
                conv.add_assistant_tool_calls(response.content, response.tool_calls)

                for tool_call in response.tool_calls:
                    result = self._handle_tool_call(state, conv, tool_call, step)
                    if _is_permission_required(result):
                        state.status = AgentStatus.PERMISSION_REQUIRED
                        state.termination_reason = "permission_required"
                        state.error = (
                            result.error
                            or "工具返回 permission_required，已停止自动继续。"
                        )
                        self._emit_event(
                            state,
                            "permission_required",
                            step,
                            tool_name=tool_call.name,
                            metadata={
                                "error": state.error,
                                "tool_call_id": tool_call.id,
                                "arguments": tool_call.arguments,
                            },
                        )
                        self._emit_event(
                            state,
                            "agent_completed",
                            step,
                            metadata={
                                "status": state.status.value,
                                "termination_reason": state.termination_reason,
                                "error": state.error,
                                "tool_name": tool_call.name,
                            },
                        )
                        return state

            state.status = AgentStatus.MAX_STEPS
            state.termination_reason = "max_steps"
            state.error = (
                f"已达到最大步数 {self.max_steps}（迭代预算耗尽），Agent 停止。"
            )
            self._emit_event(
                state,
                "agent_completed",
                state.step,
                metadata={
                    "status": AgentStatus.MAX_STEPS.value,
                    "termination_reason": state.termination_reason,
                },
            )
            return state

        except CodeWispError as exc:
            state.status = AgentStatus.FAILED
            state.termination_reason = "failed"
            state.error = str(exc)
            self._emit_event(
                state,
                "agent_completed",
                state.step,
                metadata={
                    "status": AgentStatus.FAILED.value,
                    "termination_reason": state.termination_reason,
                    "error": str(exc),
                },
            )
            return state
        except Exception as exc:  # noqa: BLE001 — 边界：不可预期错误 → FAILED
            state.status = AgentStatus.FAILED
            state.termination_reason = "failed"
            state.error = f"Agent 运行失败：{exc}"
            self._emit_event(
                state,
                "agent_completed",
                state.step,
                metadata={
                    "status": AgentStatus.FAILED.value,
                    "termination_reason": state.termination_reason,
                    "error": state.error,
                },
            )
            return state

    def _call_llm(
        self,
        state: AgentState,
        conversation: Conversation,
        tools: list[dict[str, Any]],
    ) -> LLMResponse:
        def on_text_delta(delta: str) -> None:
            self._event_sink.emit(
                AgentEvent(
                    event_type="answer_delta",
                    step=state.step,
                    metadata={"delta": delta},
                )
            )

        def on_text_discard() -> None:
            # 本回合随后转为 tool_calls：清掉已流式的推测正文
            self._event_sink.emit(
                AgentEvent(
                    event_type="answer_discard",
                    step=state.step,
                    metadata={},
                )
            )

        # V1.0：分层 Context 视图；durable conversation 不被 compaction 删除
        model_conversation = conversation
        if self.context_manager is not None:
            model_conversation = self.context_manager.build_context(
                conversation, tools=tools
            )

        chat_stream = getattr(self.llm, "chat_stream", None)
        if callable(chat_stream):
            return chat_stream(
                model_conversation,
                tools=tools,
                on_text_delta=on_text_delta,
                on_text_discard=on_text_discard,
            )
        return self.llm.chat(model_conversation, tools=tools)

    def _handle_tool_call(
        self,
        state: AgentState,
        conversation: Conversation,
        tool_call: ToolCall,
        step: int,
    ) -> ToolResult:
        self._emit_event(
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

        if tool_call.parse_error:
            result = ToolResult(
                success=False,
                output=None,
                error=f"工具参数非法：{tool_call.parse_error}",
                metadata={"tool_name": tool_call.name, "tool_call_id": tool_call.id},
            )
        elif not (tool_call.name or "").strip():
            result = ToolResult(
                success=False,
                output=None,
                error="工具名称为空。",
                metadata={"tool_call_id": tool_call.id},
            )
        else:
            result = self.executor.execute(tool_call.name, tool_call.arguments)

        event_type = "tool_completed" if result.success else "tool_failed"
        meta = result.to_dict()
        if isinstance(tool_call.arguments, dict):
            meta.setdefault("arguments", tool_call.arguments)
        self._emit_event(
            state,
            event_type,
            step,
            tool_name=tool_call.name,
            metadata=meta,
        )

        observation = self._format_observation(result)
        if self.context_manager is not None:
            observation = self.context_manager.prune_observation(
                observation, tool_name=tool_call.name
            )
            self.context_manager.update_after_tool(
                tool_name=tool_call.name,
                tool_call_id=tool_call.id or f"call_step{step}",
                arguments=tool_call.arguments if isinstance(tool_call.arguments, dict) else {},
                result=result,
                observation=observation,
            )
        call_id = tool_call.id or f"call_step{step}"
        conversation.add_tool_result(call_id, observation)
        return result

    @staticmethod
    def _format_observation(result: ToolResult) -> str:
        """将 ToolResult 转为模型可读的 observation 文本。"""
        return json.dumps(result.to_dict(), ensure_ascii=False)

    def _emit_event(
        self,
        state: AgentState,
        event_type: str,
        step: int,
        *,
        tool_name: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        event = AgentEvent(
            event_type=event_type,
            step=step,
            tool_name=tool_name,
            metadata=metadata or {},
        )
        state.events.append(event)
        self._event_sink.emit(event)


def _is_permission_required(result: ToolResult) -> bool:
    """无交互 Handler 时的硬停信号：仅当明确 permission_required。"""
    if result.metadata.get("permission_required") is True:
        return True
    output = result.output
    if isinstance(output, dict) and output.get("permission_required") is True:
        return True
    return False
