"""AgentService：Session → Conversation → AgentLoop → Persistence。

不在 AgentLoop 内访问 SQLite；运行结束后根据 AgentState / events / 新增消息落库。
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator

from backend.app.agent.loop import DEFAULT_AGENT_SYSTEM_PROMPT, DEFAULT_MAX_STEPS, AgentLoop
from backend.app.agent.state import AgentState, AgentStatus
from backend.app.llm.client import LLMClient
from backend.app.llm.messages import Message
from backend.app.llm.response import ToolCall
from backend.app.persistence.agent_run_repository import AgentRunRepository
from backend.app.persistence.conversation_repository import ConversationRepository
from backend.app.persistence.store import SqliteStore
from backend.app.session.errors import (
    InvalidMessageError,
    InvalidWorkspaceError,
    SessionBusyError,
)
from backend.app.session.models import AgentRun, AgentStep, Session
from backend.app.session.resume import SessionResumeState
from backend.app.session.service import SessionService
from backend.app.tools.executor import ToolExecutor
from backend.app.tools.factory import create_default_registry
from backend.app.tools.result import ToolResult
from backend.app.workspace.errors import WorkspaceError
from backend.app.workspace.workspace import Workspace

LLMFactory = Callable[[Session], LLMClient]


@dataclass(frozen=True)
class AgentRunResult:
    """一次 AgentService.run 的对外结果。"""

    session: Session
    run: AgentRun
    state: AgentState
    steps: tuple[AgentStep, ...] = ()
    persisted_message_ids: tuple[str, ...] = ()


class AgentService:
    """编排一次用户消息的 Agent 执行并持久化 Run / Step / Message / ToolCall。"""

    def __init__(
        self,
        store: SqliteStore,
        *,
        llm: LLMClient | None = None,
        llm_factory: LLMFactory | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
        system_prompt: str = DEFAULT_AGENT_SYSTEM_PROMPT,
    ) -> None:
        if llm is None and llm_factory is None:
            raise ValueError("必须提供 llm 或 llm_factory")
        self._store = store
        self._llm = llm
        self._llm_factory = llm_factory
        self._max_steps = max_steps
        self._system_prompt = system_prompt
        self.sessions = SessionService(store)
        self._runs = AgentRunRepository(store)
        self._conversations = ConversationRepository(store)
        self._lock_guard = threading.Lock()
        self._session_locks: dict[str, threading.Lock] = {}

    def resume(self, session_id: str) -> SessionResumeState:
        """恢复 Session 历史（不跑 Agent）。等价于 ``sessions.resume_session``。"""
        return self.sessions.resume_session(session_id)

    def continue_session(self, session_id: str, content: str) -> AgentRunResult:
        """在已恢复的 Session 上继续一轮任务（``run`` 的语义别名）。"""
        return self.run(session_id, content)

    def _resolve_llm(self, session: Session) -> LLMClient:
        if self._llm_factory is not None:
            return self._llm_factory(session)
        assert self._llm is not None
        return self._llm

    @contextmanager
    def _exclusive_session(self, session_id: str) -> Iterator[None]:
        with self._lock_guard:
            lock = self._session_locks.setdefault(session_id, threading.Lock())
        acquired = lock.acquire(blocking=False)
        if not acquired:
            raise SessionBusyError(f"Session 正在运行 Agent: {session_id}")
        try:
            yield
        finally:
            lock.release()

    def run(self, session_id: str, content: str) -> AgentRunResult:
        text = (content or "").strip()
        if not text:
            raise InvalidMessageError("消息内容不能为空")

        session = self.sessions.get_session(session_id)

        with self._exclusive_session(session_id):
            return self._run_locked(session, text)

    def _run_locked(self, session: Session, text: str) -> AgentRunResult:
        try:
            workspace = Workspace(session.workspace)
        except WorkspaceError as exc:
            raise InvalidWorkspaceError(str(exc)) from exc

        conversation = self._conversations.load_conversation(session.session_id)
        persist_from = len(conversation.messages)
        # 仅在全新空对话时写入 system；Resume 后已有 system，禁止重复追加
        if persist_from == 0 and not any(m.role == "system" for m in conversation.messages):
            conversation.add_system(self._system_prompt)

        run = self._runs.create_run(
            AgentRun.create(
                session_id=session.session_id,
                provider_id=session.provider_id,
                model_id=session.model_id,
                status=AgentStatus.RUNNING.value,
                max_steps=self._max_steps,
            )
        )

        registry = create_default_registry(workspace=workspace)
        executor = ToolExecutor(registry)
        llm = self._resolve_llm(session)
        loop = AgentLoop(
            llm,
            executor,
            registry,
            max_steps=self._max_steps,
            system_prompt=self._system_prompt,
        )

        state = loop.run(text, conversation=conversation)

        step_index_to_id, tool_call_to_step = self._persist_steps_and_tools(
            session=session,
            run=run,
            state=state,
        )

        persisted_ids: list[str] = []
        new_messages = conversation.messages[persist_from:]
        for msg in new_messages:
            step_id = _resolve_message_step_id(
                msg,
                state=state,
                step_index_to_id=step_index_to_id,
                tool_call_to_step=tool_call_to_step,
            )
            stored = self._conversations.append_message(
                session.session_id,
                Message(
                    role=msg.role,
                    content=msg.content,
                    tool_calls=msg.tool_calls,
                    tool_call_id=msg.tool_call_id,
                    agent_run_id=run.agent_run_id,
                    step_id=step_id,
                ),
            )
            if stored.message_id:
                persisted_ids.append(stored.message_id)

        completed = self._runs.complete_run(
            run.agent_run_id,
            status=state.status.value,
            termination_reason=state.termination_reason,
            final_answer=state.final_answer,
            error=state.error,
        )

        updated_session = self.sessions.touch_session(session.session_id)
        steps = tuple(self._runs.list_steps(run.agent_run_id))

        return AgentRunResult(
            session=updated_session,
            run=completed,
            state=state,
            steps=steps,
            persisted_message_ids=tuple(persisted_ids),
        )

#持久化agent工作步骤和工具调用
    def _persist_steps_and_tools(
        self,
        *,
        session: Session,
        run: AgentRun,
        state: AgentState,
    ) -> tuple[dict[int, str], dict[str, str]]:
        """根据 AgentEvent 写入 AgentStep / ToolCall；返回映射表。"""
        step_indices = sorted(
            {event.step for event in state.events if event.step >= 1}
        )
        if not step_indices and state.step >= 1:
            step_indices = list(range(1, state.step + 1))

        step_index_to_id: dict[int, str] = {}
        for index in step_indices:
            step = self._runs.add_step(
                AgentStep.create(
                    agent_run_id=run.agent_run_id,
                    session_id=session.session_id,
                    step_index=index,
                    status="completed",
                )
            )
            step_index_to_id[index] = step.step_id
            self._runs.complete_step(step.step_id, status="completed")

        tool_call_to_step: dict[str, str] = {}
        pending_by_step: dict[int, list[ToolCall]] = {}

        for event in state.events:
            if event.event_type == "tool_called":
                meta = event.metadata or {}
                # 与 AgentLoop._handle_tool_call 的 call_id 兜底保持一致，便于关联 Observation
                call_id = str(meta.get("tool_call_id") or "").strip()
                if not call_id:
                    call_id = f"call_step{event.step}"
                tc = ToolCall(
                    id=call_id,
                    name=event.tool_name or "",
                    arguments=dict(meta.get("arguments") or {}),
                    parse_error=meta.get("parse_error"),
                )
                pending_by_step.setdefault(event.step, []).append(tc)
            elif event.event_type in {"tool_completed", "tool_failed"}:
                queue = pending_by_step.get(event.step) or []
                if not queue:
                    continue
                tc = queue.pop(0)
                step_id = step_index_to_id.get(event.step)
                if not step_id:
                    continue
                result = ToolResult.from_dict(event.metadata or {"success": False})
                persisted = self._runs.add_tool_call(
                    session_id=session.session_id,
                    agent_run_id=run.agent_run_id,
                    step_id=step_id,
                    tool_call=tc,
                    result=result,
                )
                tool_call_to_step[persisted.tool_call_id] = step_id
                # 若事件里的 id 与稳定 id 不同，一并索引
                raw_id = str((event.metadata or {}).get("tool_call_id") or "")
                if raw_id:
                    tool_call_to_step[raw_id] = step_id
                if tc.id:
                    tool_call_to_step[tc.id] = step_id

        return step_index_to_id, tool_call_to_step

#解析一条消息的步骤id
def _resolve_message_step_id(
    msg: Message,
    *,
    state: AgentState,
    step_index_to_id: dict[int, str],
    tool_call_to_step: dict[str, str],
) -> str | None:
    if msg.role == "tool" and msg.tool_call_id:
        return tool_call_to_step.get(msg.tool_call_id)
    if msg.role == "assistant" and msg.tool_calls:
        for tc in msg.tool_calls:
            if tc.id in tool_call_to_step:
                return tool_call_to_step[tc.id]
        # 回退：按当前 state.step 不可靠（多 step）；用最小 step
        if step_index_to_id:
            return step_index_to_id[min(step_index_to_id)]
        return None
    if msg.role == "assistant" and not msg.tool_calls and state.step >= 1:
        return step_index_to_id.get(state.step)
    return None
