"""Session 恢复视图（V0.6 Phase 2-E）。

进程重启后通过 ``SessionService.resume_session`` 加载，
再调用 ``AgentService.run`` 即可在完整历史上继续。
"""
#退出一个session后，重新进入，恢复一个session
from __future__ import annotations

from dataclasses import dataclass

from backend.app.llm.messages import Conversation
from backend.app.session.models import AgentRun, Session


#一次Session恢复所需的只读快照
@dataclass(frozen=True)
class SessionResumeState:
    """一次 Session 恢复所需的只读快照。"""

    session: Session
    conversation: Conversation
    runs: tuple[AgentRun, ...]

    @property
    def session_id(self) -> str:
        return self.session.session_id

    @property
    def workspace(self) -> str:
        return self.session.workspace

    @property
    def provider_id(self) -> str:
        return self.session.provider_id

    @property
    def model_id(self) -> str:
        return self.session.model_id

    @property
    def message_count(self) -> int:
        return len(self.conversation.messages)

    @property
    def run_count(self) -> int:
        return len(self.runs)

    @property
    def latest_run(self) -> AgentRun | None:
        if not self.runs:
            return None
        return self.runs[-1]

    @property
    def has_history(self) -> bool:
        return self.message_count > 0
