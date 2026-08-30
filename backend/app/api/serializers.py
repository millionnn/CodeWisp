"""领域对象 → API schema 映射。"""
#将领域对象转换为api的响应
from __future__ import annotations

from backend.app.api.schemas import (
    AgentEventResponse,
    AgentRunResponse,
    AgentStepResponse,
    MessageResponse,
    PostMessageResponse,
    SessionResponse,
    ToolCallPayload,
)
from backend.app.llm.messages import Message
from backend.app.services.agent_service import AgentRunResult
from backend.app.session.models import AgentRun, AgentStep, Session


#将一个session转换为api的响应
def session_to_response(session: Session) -> SessionResponse:
    return SessionResponse(
        session_id=session.session_id,
        title=session.title,
        workspace=session.workspace,
        provider_id=session.provider_id,
        model_id=session.model_id,
        status=session.status,
        created_at=session.created_at,
        updated_at=session.updated_at,
    )

#将一个消息转换为api的响应
def message_to_response(message: Message) -> MessageResponse:
    return MessageResponse(
        message_id=message.message_id,
        session_id=message.session_id,
        agent_run_id=message.agent_run_id,
        step_id=message.step_id,
        seq=message.seq,
        role=message.role,
        content=message.content,
        tool_call_id=message.tool_call_id,
        tool_calls=[
            ToolCallPayload(
                id=tc.id,
                name=tc.name,
                arguments=dict(tc.arguments),
                arguments_raw=tc.arguments_raw,
                parse_error=tc.parse_error,
            )
            for tc in message.tool_calls
        ],
        created_at=message.created_at,
    )

#将一个agent工作转换为api的响应
def run_to_response(run: AgentRun) -> AgentRunResponse:
    return AgentRunResponse(
        agent_run_id=run.agent_run_id,
        session_id=run.session_id,
        provider_id=run.provider_id,
        model_id=run.model_id,
        status=run.status,
        termination_reason=run.termination_reason,
        max_steps=run.max_steps,
        final_answer=run.final_answer,
        error=run.error,
        created_at=run.created_at,
        completed_at=run.completed_at,
    )

#将一个agent工作步骤转换为api的响应
def step_to_response(step: AgentStep) -> AgentStepResponse:
    return AgentStepResponse(
        step_id=step.step_id,
        agent_run_id=step.agent_run_id,
        session_id=step.session_id,
        step_index=step.step_index,
        status=step.status,
        created_at=step.created_at,
        completed_at=step.completed_at,
    )

#将一个agent工作结果转换为api的响应
def agent_result_to_response(
    result: AgentRunResult,
    *,
    messages: list[Message],
) -> PostMessageResponse:
    return PostMessageResponse(
        session=session_to_response(result.session),
        run=run_to_response(result.run),
        steps=[step_to_response(s) for s in result.steps],
        final_answer=result.state.final_answer,
        status=result.state.status.value,
        termination_reason=result.state.termination_reason,
        error=result.state.error,
        messages=[message_to_response(m) for m in messages],
        events=[
            AgentEventResponse(
                event_type=e.event_type,
                step=e.step,
                timestamp=e.timestamp,
                tool_name=e.tool_name,
                metadata=dict(e.metadata or {}),
            )
            for e in result.state.events
        ],
    )
