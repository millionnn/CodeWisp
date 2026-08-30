"""SessionService：Session / Conversation 用例层（不编排 AgentLoop）。"""
#服务层，解耦loop层以及底层数据库层
from __future__ import annotations

from pathlib import Path

from backend.app.llm.messages import Conversation, Message
from backend.app.persistence.agent_run_repository import AgentRunRepository
from backend.app.persistence.conversation_repository import ConversationRepository
from backend.app.persistence.errors import NotFoundError
from backend.app.persistence.session_repository import SessionRepository
from backend.app.persistence.store import SqliteStore
from backend.app.session.errors import InvalidSessionError, InvalidWorkspaceError, SessionNotFoundError
from backend.app.session.models import AgentRun, AgentStep, Session
from backend.app.session.resume import SessionResumeState


class SessionService:
    def __init__(self, store: SqliteStore) -> None:
        self._store = store
        self.sessions = SessionRepository(store)
        self.conversations = ConversationRepository(store)
        self.runs = AgentRunRepository(store)

    def create_session(
        self,
        *,
        title: str,
        workspace: str | Path,
        provider_id: str = "deepseek",
        model_id: str = "deepseek-chat",
        status: str = "active",
    ) -> Session:
        title_text = (title or "").strip()
        if not title_text:
            raise InvalidSessionError("title 不能为空")
        provider = (provider_id or "").strip()
        model = (model_id or "").strip()
        if not provider or not model:
            raise InvalidSessionError("provider_id / model_id 不能为空")

        root = Path(workspace).expanduser().resolve()
        if not root.exists() or not root.is_dir():
            raise InvalidWorkspaceError(f"workspace 无效: {root}")

        session = Session.create(
            title=title_text,
            workspace=str(root),
            provider_id=provider,
            model_id=model,
            status=status,
        )
        return self.sessions.create(session)

    def get_session(self, session_id: str) -> Session:
        try:
            return self.sessions.get(session_id)
        except NotFoundError as exc:
            raise SessionNotFoundError(str(exc)) from exc

    def list_sessions(self, *, limit: int = 100, offset: int = 0) -> list[Session]:
        return self.sessions.list(limit=limit, offset=offset)

    def rename_session(self, session_id: str, title: str) -> Session:
        title_text = (title or "").strip()
        if not title_text:
            raise InvalidSessionError("title 不能为空")
        try:
            return self.sessions.rename(session_id, title_text)
        except NotFoundError as exc:
            raise SessionNotFoundError(str(exc)) from exc

    def update_session(
        self,
        session_id: str,
        *,
        title: str | None = None,
        status: str | None = None,
        provider_id: str | None = None,
        model_id: str | None = None,
    ) -> Session:
        try:
            return self.sessions.update(
                session_id,
                title=title,
                status=status,
                provider_id=provider_id,
                model_id=model_id,
            )
        except NotFoundError as exc:
            raise SessionNotFoundError(str(exc)) from exc

    def delete_session(self, session_id: str) -> None:
        try:
            self.sessions.delete(session_id)
        except NotFoundError as exc:
            raise SessionNotFoundError(str(exc)) from exc

    def load_conversation(self, session_id: str) -> Conversation:
        self.get_session(session_id)
        return self.conversations.load_conversation(session_id)

    def append_message(self, session_id: str, message: Message) -> Message:
        self.get_session(session_id)
        return self.conversations.append_message(session_id, message)

    def touch_session(self, session_id: str) -> Session:
        """仅刷新 updated_at（通过 no-op update）。"""
        session = self.get_session(session_id)
        return self.sessions.update(session_id, title=session.title)

    def list_runs(self, session_id: str) -> list[AgentRun]:
        self.get_session(session_id)
        return self.runs.list_runs(session_id)

    def list_steps(self, agent_run_id: str) -> list[AgentStep]:
        return self.runs.list_steps(agent_run_id)

    def resume_session(self, session_id: str) -> SessionResumeState:
        """进程重启后恢复 Session：元数据 + 完整 Conversation + AgentRun 列表。

        不执行 Agent。继续对话请再调用 ``AgentService.run(session_id, content)``。
        """
        session = self.get_session(session_id)
        conversation = self.conversations.load_conversation(session_id)
        runs = tuple(self.runs.list_runs(session_id))
        return SessionResumeState(
            session=session,
            conversation=conversation,
            runs=runs,
        )
