"""AgentService：Session → ModelResolver → AgentLoop → Persistence。

不在 AgentLoop 内访问 SQLite / Registry；按 Session 身份 resolve LLM 后注入 Loop。
"""

from __future__ import annotations

import threading
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Callable, Iterator

from backend.app.agent.event_sink import (
    AgentEventSink,
    CompositeEventSink,
    NullEventSink,
    RecordingEventSink,
)
from backend.app.agent.events import AgentEvent
from backend.app.agent.loop import DEFAULT_AGENT_SYSTEM_PROMPT, DEFAULT_MAX_STEPS, AgentLoop
from backend.app.agent.state import AgentState, AgentStatus
from backend.app.changes.diff import compute_file_diffs
from backend.app.changes.models import (
    ChangeType,
    FileChangeRecord,
    FileDiff,
    RevertReport,
    WorkspaceSnapshot,
)
from backend.app.changes.revert import RevertService
from backend.app.changes.tracker import WriteChangeTracker
from backend.app.context.budget import ContextBudget
from backend.app.context.manager import DefaultContextManager
from backend.app.git.context import GitContextProvider
from backend.app.git.models import CommitPreview, GitBranch, GitCommit, GitDiff, GitRepositoryInfo, GitStatus
from backend.app.git.service import GitService
from backend.app.lsp.context import LSPContextProvider
from backend.app.lsp.manager import LanguageServerManager, get_default_manager
from backend.app.lsp.models import (
    DefinitionResult,
    Diagnostic,
    HoverResult,
    LspStatus,
    ReferenceResult,
    Symbol,
)
from backend.app.lsp.service import LSPService
from backend.app.context.models import (
    CheckpointTrigger,
    ContextCheckpoint,
    ContextStatus,
    MemoryItem,
    Plan,
    TaskState,
)
from backend.app.llm.client import LLMClient
from backend.app.llm.messages import Message
from backend.app.llm.response import ToolCall
from backend.app.memory.models import IndexStats, RetrievedContext, TaskRunSummary
from backend.app.memory.service import MemoryService
from backend.app.persistence.agent_run_repository import AgentRunRepository
from backend.app.persistence.context_repository import ContextRepository
from backend.app.persistence.conversation_repository import ConversationRepository
from backend.app.persistence.snapshot_repository import SnapshotRepository
from backend.app.persistence.store import SqliteStore
from backend.app.planning.service import PlannerService
from backend.app.permissions.decision import PermissionDecision
from backend.app.permissions.handler import AlwaysAllowPermissionHandler, PermissionHandler
from backend.app.permissions.request import PermissionRequest
from backend.app.providers.errors import (
    InvalidModelError,
    UnknownModelError,
)
from backend.app.providers.model import Model
from backend.app.providers.provider import Provider
from backend.app.providers.resolver import ModelResolver, ResolvedModel
from backend.app.session.errors import (
    InvalidMessageError,
    InvalidSessionError,
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


def _is_scripted_llm(llm: LLMClient) -> bool:
    """测试用 ScriptedLLM 带有限响应队列；不可再用于 Planner/Memory 旁路调用。"""
    return hasattr(llm, "_queue") or hasattr(llm, "_responses")


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
        model_resolver: ModelResolver | None = None,
        permission_handler: PermissionHandler | None = None,
        event_sink: AgentEventSink | None = None,
        max_steps: int = DEFAULT_MAX_STEPS,
        system_prompt: str = DEFAULT_AGENT_SYSTEM_PROMPT,
    ) -> None:
        if llm is None and llm_factory is None and model_resolver is None:
            raise ValueError("必须提供 llm、llm_factory 或 model_resolver")
        self._store = store
        self._llm = llm
        self._llm_factory = llm_factory
        self._model_resolver = model_resolver
        self._permission_handler = permission_handler
        self._event_sink: AgentEventSink = event_sink or NullEventSink()
        self._max_steps = max_steps
        self._system_prompt = system_prompt
        self.sessions = SessionService(store)
        self._runs = AgentRunRepository(store)
        self._conversations = ConversationRepository(store)
        self._snapshots = SnapshotRepository(store)
        self._context = ContextRepository(store)
        self._memory = MemoryService(store)
        self._planner = PlannerService(repository=self._context)
        self._lock_guard = threading.Lock()
        self._session_locks: dict[str, threading.Lock] = {}
        # 进程内缓存：供 CLI /context 诊断（重启后可从 SQLite 重建）
        self._context_managers: dict[str, DefaultContextManager] = {}
        self._lsp_manager: LanguageServerManager = get_default_manager()

    def resume(self, session_id: str) -> SessionResumeState:
        """恢复 Session 历史（不跑 Agent）。等价于 ``sessions.resume_session``。"""
        return self.sessions.resume_session(session_id)

    def continue_session(self, session_id: str, content: str) -> AgentRunResult:
        """在已恢复的 Session 上继续一轮任务（``run`` 的语义别名）。"""
        return self.run(session_id, content)

    def resolve_model(self, session: Session) -> ResolvedModel | None:
        """若配置了 ModelResolver，返回本次 Session 身份对应的 ResolvedModel。"""
        if self._model_resolver is None:
            return None
        return self._model_resolver.resolve(session.provider_id, session.model_id)

    @property
    def model_resolver(self) -> ModelResolver | None:
        return self._model_resolver

    @property
    def max_steps(self) -> int:
        return self._max_steps

    @property
    def db_path(self) -> str:
        return str(self._store.path)

    def require_resolver(self) -> ModelResolver:
        if self._model_resolver is None:
            raise InvalidSessionError(
                "当前 AgentService 未配置 ModelResolver，无法列出/切换模型。"
            )
        return self._model_resolver

    #列出所有供应商
    def list_providers(self) -> list[Provider]:
        return self.require_resolver().providers.list()

    #列出所有模型
    def list_models(self, provider_id: str | None = None) -> list[Model]:
        resolver = self.require_resolver()
        if provider_id:
            return resolver.models.list_for_provider(provider_id)
        return resolver.models.list()

    #切换会话模型
    def switch_session_model(
        self,
        session_id: str,
        *,
        provider_id: str,
        model_id: str,
    ) -> Session:
        """校验 Registry 后更新 Session 模型身份（不立刻建 LLMClient）。"""
        resolver = self.require_resolver()
        resolver.lookup(provider_id, model_id)
        return self.sessions.update_session(
            session_id,
            provider_id=provider_id,
            model_id=model_id,
        )

    def parse_model_ref(
        self,
        *parts: str,
        current_provider_id: str | None = None,
    ) -> tuple[str, str]:
        """解析 CLI ``/model`` 参数 → (provider_id, model_id)。

        支持：
        - ``provider model``
        - 单独 ``model_id``（全局唯一时；否则若当前 provider 下存在则用之）
        """
        resolver = self.require_resolver()
        tokens = [p.strip() for p in parts if p and p.strip()]
        if not tokens:
            raise InvalidModelError("请指定 model_id，或 provider_id + model_id")

        if len(tokens) >= 2:
            return tokens[0], tokens[1]

        model_token = tokens[0]
        matches = resolver.find_models_by_id(model_token)
        if len(matches) == 1:
            return matches[0].provider_id, matches[0].model_id
        if len(matches) > 1 and current_provider_id:
            for m in matches:
                if m.provider_id == current_provider_id:
                    return m.provider_id, m.model_id
            raise UnknownModelError(
                f"模型 {model_token!r} 对应多个 Provider："
                + ", ".join(sorted({m.provider_id for m in matches}))
                + "。请使用: /model <provider> <model>"
            )
        if len(matches) > 1:
            raise UnknownModelError(
                f"模型 {model_token!r} 对应多个 Provider："
                + ", ".join(sorted({m.provider_id for m in matches}))
                + "。请使用: /model <provider> <model>"
            )
        # 零匹配：若当前 provider 下 lookup 失败，给出 unknown
        if current_provider_id and resolver.models.contains(
            current_provider_id, model_token
        ):
            return current_provider_id, model_token
        raise UnknownModelError(f"未知模型: {model_token}")

    def list_run_file_changes(self, agent_run_id: str) -> list[FileChangeRecord]:
        """列出某次 AgentRun 产生的文件变更。"""
        return self._snapshots.list_file_changes(agent_run_id=agent_run_id)

    def list_step_file_changes(self, step_id: str) -> list[FileChangeRecord]:
        """列出某个 AgentStep 产生的文件变更。"""
        return self._snapshots.list_file_changes(agent_step_id=step_id)

    def get_step_snapshots(
        self, step_id: str
    ) -> tuple[WorkspaceSnapshot | None, WorkspaceSnapshot | None]:
        """返回 Step 的 pre_step / post_step Snapshot（若有写操作）。"""
        return self._snapshots.get_step_boundary_snapshots(step_id)

    def get_snapshot(self, snapshot_id: str) -> WorkspaceSnapshot:
        return self._snapshots.get_snapshot(snapshot_id)

    def get_step_file_diffs(self, step_id: str) -> list[FileDiff]:
        """Step 的 pre_step vs post_step Diff。"""
        before, after = self.get_step_snapshots(step_id)
        if before is None or after is None:
            return []
        return compute_file_diffs(before, after)

    def get_run_file_diffs(self, agent_run_id: str) -> list[FileDiff]:
        """Run 内全部 FileChange 对应的 Diff（按 path 去重，后者覆盖）。"""
        changes = self.list_run_file_changes(agent_run_id)
        by_path: dict[str, FileDiff] = {}
        for change in changes:
            by_path[change.path] = self._file_change_to_diff(change)
        return [by_path[k] for k in sorted(by_path)]

    def _file_change_to_diff(self, change: FileChangeRecord) -> FileDiff:
        before_text: str | None = None
        after_text: str | None = None
        if change.before_snapshot_id:
            snap = self._snapshots.get_snapshot(change.before_snapshot_id)
            f = snap.file_map().get(change.path)
            if f and f.exists:
                before_text = f.content
        if change.after_snapshot_id:
            snap = self._snapshots.get_snapshot(change.after_snapshot_id)
            f = snap.file_map().get(change.path)
            if f and f.exists:
                after_text = f.content
        return FileDiff(
            path=change.path,
            change_type=change.change_type,
            before=before_text,
            after=after_text,
        )

    def revert_step(
        self,
        step_id: str,
        *,
        permission_handler: PermissionHandler | None = None,
        event_sink: AgentEventSink | None = None,
    ) -> RevertReport:
        """恢复指定 AgentStep 对工作区的修改；不删除历史记录。"""
        step = self._runs.get_step(step_id)
        session = self.sessions.get_session(step.session_id)
        try:
            workspace = Workspace(session.workspace)
        except WorkspaceError as exc:
            raise InvalidWorkspaceError(str(exc)) from exc
        service = RevertService(
            workspace,
            self._snapshots,
            permission_handler=(
                permission_handler
                if permission_handler is not None
                else self._permission_handler
            ),
            event_sink=event_sink or self._event_sink,
        )
        report = service.revert_step(step, session_workspace=session.workspace)
        if report.ok:
            paths = list(report.applied) if report.applied else None
            self._invalidate_context(session.session_id, session.workspace, paths=paths)
        return report

    def revert_run(
        self,
        agent_run_id: str,
        *,
        permission_handler: PermissionHandler | None = None,
        event_sink: AgentEventSink | None = None,
    ) -> RevertReport:
        """倒序恢复 AgentRun 内各 Step 的写修改；不删除历史记录。"""
        run = self._runs.get_run(agent_run_id)
        session = self.sessions.get_session(run.session_id)
        try:
            workspace = Workspace(session.workspace)
        except WorkspaceError as exc:
            raise InvalidWorkspaceError(str(exc)) from exc
        steps = self._runs.list_steps(agent_run_id)
        service = RevertService(
            workspace,
            self._snapshots,
            permission_handler=(
                permission_handler
                if permission_handler is not None
                else self._permission_handler
            ),
            event_sink=event_sink or self._event_sink,
        )
        report = service.revert_run(
            run, steps, session_workspace=session.workspace
        )
        if report.ok:
            paths = list(report.applied) if report.applied else None
            self._invalidate_context(session.session_id, session.workspace, paths=paths)
        return report

    # ── V1.0 Context / Plan 边界（CLI / 未来 Web）────────────────

    def get_context_manager(self, session_id: str) -> DefaultContextManager:
        session = self.sessions.get_session(session_id)
        return self._get_or_create_context_manager(session)

    def get_context_status(self, session_id: str) -> ContextStatus:
        session = self.sessions.get_session(session_id)
        cm = self._get_or_create_context_manager(session)
        conversation = self._conversations.load_conversation(session_id)
        return cm.status(conversation)

    def compact_context(
        self,
        session_id: str,
        *,
        trigger: CheckpointTrigger = CheckpointTrigger.MANUAL,
    ) -> ContextCheckpoint:
        session = self.sessions.get_session(session_id)
        cm = self._get_or_create_context_manager(session)
        conversation = self._conversations.load_conversation(session_id)
        return cm.compact(conversation, trigger=trigger)

    def list_memories(self, session_id: str, *, include_invalidated: bool = False) -> list[MemoryItem]:
        self.sessions.get_session(session_id)
        return self._context.list_memories(
            session_id, include_invalidated=include_invalidated
        )

    def get_active_task(self, session_id: str) -> TaskState | None:
        self.sessions.get_session(session_id)
        return self._context.get_active_task(session_id)

    def get_latest_plan(self, session_id: str) -> Plan | None:
        self.sessions.get_session(session_id)
        return self._context.get_latest_plan(session_id)

    def list_plans(self, session_id: str) -> list[Plan]:
        self.sessions.get_session(session_id)
        return self._context.list_plans(session_id)

    def refresh_plan(self, session_id: str) -> Plan:
        session = self.sessions.get_session(session_id)
        cm = self._get_or_create_context_manager(session)
        llm, _, _ = self._resolve_runtime(session)
        self._planner.set_llm(llm)
        cm.refresh_project_rules(focus_path=None)
        goal = cm.task.goal if cm.task else "continue"
        cm.refresh_retrieval(goal)
        memories = "\n".join(m.render_line() for m in cm.memories if not m.invalidated)
        retrieved = "\n\n".join(
            getattr(r, "render", lambda: str(r))() for r in cm.retrieved[:6]
        )
        plan = self._planner.refresh_plan(
            session_id=session_id,
            goal=goal,
            project_rules=cm.project_rules.render(),
            retrieved=retrieved,
            memories=memories,
        )
        cm.plan = plan
        return plan

    def memory_search(
        self, session_id: str, query: str, *, top_k: int = 10
    ) -> list[RetrievedContext]:
        session = self.sessions.get_session(session_id)
        self._memory.ensure_index(session.workspace)
        return self._memory.search(
            session.workspace, query, session_id=session_id, top_k=top_k
        )

    def memory_index(self, session_id: str) -> IndexStats:
        session = self.sessions.get_session(session_id)
        return self._memory.index_workspace(session.workspace)

    def memory_rebuild(self, session_id: str) -> IndexStats:
        session = self.sessions.get_session(session_id)
        return self._memory.rebuild_index(session.workspace)

    def memory_stats(self, session_id: str) -> IndexStats:
        session = self.sessions.get_session(session_id)
        return self._memory.stats(session.workspace)

    def get_context_bundle(self, session_id: str) -> dict:
        """未来 Web / API：上下文诊断包。"""
        status = self.get_context_status(session_id)
        plan = self.get_latest_plan(session_id)
        task = self.get_active_task(session_id)
        return {
            "status": status.to_dict(),
            "task": task.to_dict() if task else None,
            "plan": plan.to_dict() if plan else None,
            "memories": [m.to_dict() for m in self.list_memories(session_id)],
        }

    # ── V1.1 Git boundary ────────────────────────────────────────

    def _git_service_for_session(self, session_id: str) -> GitService:
        session = self.sessions.get_session(session_id)
        return GitService(Workspace(session.workspace))

    def git_detect(self, session_id: str) -> GitRepositoryInfo:
        return self._git_service_for_session(session_id).detect()

    def git_status(self, session_id: str) -> GitStatus | GitRepositoryInfo:
        return self._git_service_for_session(session_id).status()

    def git_diff(
        self,
        session_id: str,
        *,
        path: str | None = None,
        staged: bool = False,
    ) -> GitDiff:
        return self._git_service_for_session(session_id).diff(path=path, staged=staged)

    def git_log(self, session_id: str, *, limit: int = 20) -> list[GitCommit]:
        return self._git_service_for_session(session_id).log(limit=limit)

    def git_branches(self, session_id: str) -> list[GitBranch]:
        return self._git_service_for_session(session_id).list_branches()

    def git_commit(
        self,
        session_id: str,
        *,
        message: str,
        paths: list[str] | None = None,
        confirm: bool = False,
        permission_handler: PermissionHandler | None = None,
    ) -> dict:
        """Commit via GitService; requires confirm=true."""
        if not confirm:
            raise InvalidMessageError("git commit 需要 confirm=true")
        service = self._git_service_for_session(session_id)
        preview = service.build_commit_preview(message, paths)

        handler = permission_handler
        if handler is not None and not isinstance(handler, AlwaysAllowPermissionHandler):
            perm_req = PermissionRequest(
                command="git",
                args=("commit", "-m", message),
                cwd=".",
                reason=f"API git commit:\n{preview.render()}",
                tool_name="git_commit",
                session_id=session_id,
            )
            decision = handler.request(perm_req)
            if decision is PermissionDecision.DENY:
                return {
                    "ok": False,
                    "denied": True,
                    "commit_preview": preview.to_dict(),
                }

        result = service.commit(message, paths)
        cm = self._context_managers.get(session_id)
        if cm is not None:
            cm.refresh_git_context()
        return {"ok": True, **result, "commit_preview": preview.to_dict()}

    def git_commit_preview(
        self,
        session_id: str,
        *,
        message: str,
        paths: list[str] | None = None,
    ) -> CommitPreview:
        return self._git_service_for_session(session_id).build_commit_preview(message, paths)

    # ── V1.2 LSP boundary ────────────────────────────────────────

    def _lsp_service_for_session(self, session_id: str) -> LSPService:
        session = self.sessions.get_session(session_id)
        return LSPService(Workspace(session.workspace), manager=self._lsp_manager)

    def lsp_status(self, session_id: str) -> LspStatus:
        return self._lsp_service_for_session(session_id).status()

    def lsp_diagnostics(
        self, session_id: str, *, path: str | None = None
    ) -> list[Diagnostic]:
        return self._lsp_service_for_session(session_id).diagnostics(path)

    def lsp_symbols(self, session_id: str, *, path: str) -> list[Symbol]:
        return self._lsp_service_for_session(session_id).symbols(path)

    def lsp_definition(
        self,
        session_id: str,
        *,
        path: str,
        line: int,
        character: int,
    ) -> DefinitionResult:
        return self._lsp_service_for_session(session_id).definition(path, line, character)

    def lsp_references(
        self,
        session_id: str,
        *,
        path: str,
        line: int,
        character: int,
    ) -> ReferenceResult:
        return self._lsp_service_for_session(session_id).references(path, line, character)

    def lsp_hover(
        self,
        session_id: str,
        *,
        path: str,
        line: int,
        character: int,
    ) -> HoverResult:
        return self._lsp_service_for_session(session_id).hover(path, line, character)

    def _context_window_for_session(self, session: Session) -> int | None:
        resolved = self.resolve_model(session)
        if resolved is not None:
            return resolved.model.context_window
        return None

    def _get_or_create_context_manager(self, session: Session) -> DefaultContextManager:
        existing = self._context_managers.get(session.session_id)
        if existing is not None:
            return existing
        budget = ContextBudget.from_context_window(
            self._context_window_for_session(session)
        )

        def on_retrieve(query: str):
            try:
                self._memory.ensure_index(session.workspace)
                return self._memory.search(
                    session.workspace, query, session_id=session.session_id, top_k=8
                )
            except Exception:  # noqa: BLE001
                return []

        cm = DefaultContextManager(
            session_id=session.session_id,
            workspace_root=session.workspace,
            budget=budget,
            repository=self._context,
            model_id=session.model_id,
            planner=self._planner,
            on_retrieve=on_retrieve,
            git_context_provider=GitContextProvider(session.workspace),
            lsp_context_provider=LSPContextProvider(
                session.workspace, manager=self._lsp_manager
            ),
        )
        cm.load()
        self._context_managers[session.session_id] = cm
        return cm

    def _invalidate_context(
        self,
        session_id: str,
        workspace: str,
        *,
        paths: list[str] | None,
    ) -> None:
        session = self.sessions.get_session(session_id)
        # 确保 manager 存在（即使尚未跑过 Agent）
        cm = self._context_managers.get(session_id)
        if cm is None:
            cm = self._get_or_create_context_manager(session)
        cm.invalidate_after_revert(paths=paths)
        if paths:
            try:
                self._memory.invalidate_paths(
                    workspace, paths, session_id=session_id
                )
            except Exception:  # noqa: BLE001
                pass

    def _resolve_runtime(self, session: Session) -> tuple[LLMClient, str, str]:
        """返回 (llm, provider_id, model_id)。优先级：llm_factory > model_resolver > llm。"""
        if self._llm_factory is not None:
            return self._llm_factory(session), session.provider_id, session.model_id
        if self._model_resolver is not None:
            resolved = self._model_resolver.resolve(
                session.provider_id,
                session.model_id,
            )
            return resolved.llm, resolved.provider_id, resolved.model_id
        assert self._llm is not None
        return self._llm, session.provider_id, session.model_id

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

    def run(
        self,
        session_id: str,
        content: str,
        *,
        event_sink: AgentEventSink | None = None,
        permission_handler: PermissionHandler | None = None,
    ) -> AgentRunResult:
        text = (content or "").strip()
        if not text:
            raise InvalidMessageError("消息内容不能为空")

        session = self.sessions.get_session(session_id)

        with self._exclusive_session(session_id):
            return self._run_locked(
                session,
                text,
                event_sink=event_sink,
                permission_handler=permission_handler,
            )

    def _run_locked(
        self,
        session: Session,
        text: str,
        *,
        event_sink: AgentEventSink | None = None,
        permission_handler: PermissionHandler | None = None,
    ) -> AgentRunResult:
        try:
            workspace = Workspace(session.workspace)
        except WorkspaceError as exc:
            raise InvalidWorkspaceError(str(exc)) from exc

        conversation = self._conversations.load_conversation(session.session_id)
        persist_from = len(conversation.messages)
        if persist_from == 0 and not any(m.role == "system" for m in conversation.messages):
            conversation.add_system(self._system_prompt)

        llm, provider_id, model_id = self._resolve_runtime(session)

        run = self._runs.create_run(
            AgentRun.create(
                session_id=session.session_id,
                provider_id=provider_id,
                model_id=model_id,
                status=AgentStatus.RUNNING.value,
                max_steps=self._max_steps,
            )
        )

        context_manager = self._get_or_create_context_manager(session)
        # 刷新预算（可能切换过模型）
        context_manager.budget = ContextBudget.from_context_window(
            self._context_window_for_session(session)
        )
        context_manager.model_id = model_id
        # 初始 Plan：真实 LLM 可驱动；ScriptedLLM（测试 _queue）则启发式，避免抢响应。
        # Loop 内 replan 始终启发式（不与主对话争抢同一 client）。
        if not _is_scripted_llm(llm):
            self._planner.set_llm(llm)
        else:
            self._planner.set_llm(None)
        context_manager._planner = self._planner  # noqa: SLF001
        try:
            self._memory.ensure_index(session.workspace)
        except Exception:  # noqa: BLE001 — 索引失败不阻断主任务
            pass

        # Plan 事件必须在 begin_run 前挂上 sink，才能实时推到 CLI/Web
        outer_sink: AgentEventSink = event_sink or self._event_sink
        recorder = RecordingEventSink()
        change_tracker = WriteChangeTracker(workspace)
        sink: AgentEventSink = CompositeEventSink(recorder, change_tracker, outer_sink)
        context_manager.set_event_emitter(sink.emit)

        try:
            context_manager.begin_run(text, agent_run_id=run.agent_run_id)
        finally:
            self._planner.set_llm(None)

        handler = (
            permission_handler
            if permission_handler is not None
            else self._permission_handler
        )

        def on_permission_wait(req: PermissionRequest) -> None:
            self._runs.update_run_status(
                run.agent_run_id,
                AgentStatus.WAITING_PERMISSION.value,
            )
            sink.emit(
                AgentEvent(
                    event_type="permission_requested",
                    step=0,
                    tool_name=req.tool_name,
                    metadata=req.to_dict(),
                )
            )

        def on_permission_resolved(
            req: PermissionRequest,
            decision: PermissionDecision | None,
        ) -> None:
            self._runs.update_run_status(
                run.agent_run_id,
                AgentStatus.RUNNING.value,
            )
            sink.emit(
                AgentEvent(
                    event_type="permission_resolved",
                    step=0,
                    tool_name=req.tool_name,
                    metadata={
                        "request_id": req.request_id,
                        "decision": decision.value if decision else "interrupted",
                    },
                )
            )

        def on_command_line(stream: str, line: str) -> None:
            sink.emit(
                AgentEvent(
                    event_type="command_output_line",
                    step=0,
                    tool_name="run_command",
                    metadata={"stream": stream, "line": line},
                )
            )

        registry = create_default_registry(
            workspace=workspace,
            permission_handler=handler,
            session_id=session.session_id,
            agent_run_id=run.agent_run_id,
            on_permission_wait=on_permission_wait if handler else None,
            on_permission_resolved=on_permission_resolved if handler else None,
            on_command_line=on_command_line,
            lsp_service=LSPService(workspace, manager=self._lsp_manager),
            plan_complete_fn=context_manager.complete_current_step,
        )
        executor = ToolExecutor(registry)
        loop = AgentLoop(
            llm,
            executor,
            registry,
            max_steps=self._max_steps,
            system_prompt=self._system_prompt,
            event_sink=sink,
            context_manager=context_manager,
        )

        state = loop.run(text, conversation=conversation)
        context_manager.set_event_emitter(None)
        # permission_* 仅经 sink 发出；用 recorder 对齐完整时间线到 state.events
        # answer_delta 只服务实时 UI，不进入持久化轨迹
        state.events = [
            e
            for e in recorder.events
            if e.event_type
            not in {"answer_delta", "answer_discard", "command_output_line"}
        ]

        step_index_to_id, tool_call_to_step = self._persist_steps_and_tools(
            session=session,
            run=run,
            state=state,
        )
        self._persist_write_changes(
            tracker=change_tracker,
            workspace=workspace,
            session=session,
            run=run,
            step_index_to_id=step_index_to_id,
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

        # V1.0+：Run 结束后异步边界内抽取 Memory / Task Summary（失败忽略）
        try:
            # 与 Agent 共用 ScriptedLLM 队列时不得抽取，否则会吃掉下一轮响应
            if not _is_scripted_llm(llm):
                self._memory.set_llm(llm)
            else:
                self._memory.set_llm(None)
            observations = [
                (m.content or "")
                for m in conversation.messages[persist_from:]
                if m.role == "tool"
            ]
            changed = list(context_manager.task.workspace_state.modified_files) if context_manager.task else []
            self._memory.extract_after_run(
                session_id=session.session_id,
                workspace=session.workspace,
                objective=text,
                final_answer=state.final_answer,
                observations=observations,
                changed_files=changed,
                agent_run_id=run.agent_run_id,
            )
            context_manager.memories = self._context.list_memories(session.session_id)
            summary = TaskRunSummary(
                summary_id="",
                session_id=session.session_id,
                workspace=session.workspace,
                objective=text,
                agent_run_id=run.agent_run_id,
                changed_files=changed,
                important_decisions=list(
                    context_manager.task.important_decisions if context_manager.task else []
                ),
                tests=list(
                    context_manager.task.workspace_state.test_results
                    if context_manager.task
                    else []
                ),
                failures=[e for e in ([state.error] if state.error else [])],
                final_result=state.termination_reason or state.status.value,
                unresolved_issues=list(
                    context_manager.task.blockers if context_manager.task else []
                ),
            )
            self._memory.save_task_summary(summary)
            if changed:
                self._memory.index_paths(session.workspace, changed)
        except Exception:  # noqa: BLE001
            pass

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

    def _persist_write_changes(
        self,
        *,
        tracker: WriteChangeTracker,
        workspace: Workspace,
        session: Session,
        run: AgentRun,
        step_index_to_id: dict[int, str],
    ) -> None:
        """将写工具 before/after 落为 Snapshot + FileChange（Loop 之后）。"""
        completed = tracker.completed
        if not completed:
            return

        by_step: dict[int, list] = {}
        for item in completed:
            by_step.setdefault(item.step_index, []).append(item)

        root = str(workspace.root)
        for step_index, items in sorted(by_step.items()):
            step_id = step_index_to_id.get(step_index)
            if not step_id:
                continue

            before_files = [t.before for t in items]
            after_files = [(t.after or t.before) for t in items]
            self._snapshots.save_snapshot(
                WorkspaceSnapshot.create(
                    workspace_root=root,
                    files=before_files,
                    reason="pre_step",
                    session_id=session.session_id,
                    agent_run_id=run.agent_run_id,
                    agent_step_id=step_id,
                )
            )
            self._snapshots.save_snapshot(
                WorkspaceSnapshot.create(
                    workspace_root=root,
                    files=after_files,
                    reason="post_step",
                    session_id=session.session_id,
                    agent_run_id=run.agent_run_id,
                    agent_step_id=step_id,
                )
            )

            for tracked in items:
                after_file = tracked.after or tracked.before
                before_snap = self._snapshots.save_snapshot(
                    WorkspaceSnapshot.create(
                        workspace_root=root,
                        files=[tracked.before],
                        reason="pre_tool",
                        session_id=session.session_id,
                        agent_run_id=run.agent_run_id,
                        agent_step_id=step_id,
                        tool_call_id=tracked.tool_call_id,
                    )
                )
                after_snap = self._snapshots.save_snapshot(
                    WorkspaceSnapshot.create(
                        workspace_root=root,
                        files=[after_file],
                        reason="post_tool",
                        session_id=session.session_id,
                        agent_run_id=run.agent_run_id,
                        agent_step_id=step_id,
                        tool_call_id=tracked.tool_call_id,
                    )
                )
                change_type = tracker.change_type_for(tracked)
                if change_type is ChangeType.UNCHANGED:
                    continue
                self._snapshots.add_file_change(
                    session_id=session.session_id,
                    agent_run_id=run.agent_run_id,
                    agent_step_id=step_id,
                    tool_call_id=tracked.tool_call_id,
                    path=tracked.path,
                    change_type=change_type,
                    before_snapshot_id=before_snap.snapshot_id,
                    after_snapshot_id=after_snap.snapshot_id,
                )


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
