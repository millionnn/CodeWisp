"""ContextManager：分层装配、预算、压缩、状态更新。

AgentLoop 只依赖本模块 Protocol；不访问 SQLite。
持久化由 DefaultContextManager（经 Repository）在 AgentService 侧完成。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol, runtime_checkable

from backend.app.context.budget import ContextBudget
from backend.app.context.memory import MemoryCandidateExtractor, candidates_to_items
from backend.app.context.plan_events import (
    PLAN_STEP_STARTED,
    event_type_for_step_status,
    plan_completed_event,
    plan_created_event,
    plan_step_event,
)
from backend.app.context.models import (
    CheckpointTrigger,
    ContextCheckpoint,
    ContextSectionUsage,
    ContextStatus,
    MemoryItem,
    MemorySourceType,
    Plan,
    PlanStatus,
    PlanStep,
    PlanStepStatus,
    TaskState,
    TaskStatus,
    WorkspaceState,
)
from backend.app.context.priority import ContextPriority
from backend.app.context.project_rules import (
    ProjectInstructionSet,
    discover_project_rules,
    merge_rules,
)
from backend.app.context.tool_output import (
    DEFAULT_TOOL_OUTPUT_POLICY,
    ToolOutputPolicy,
    extract_paths_from_tool_payload,
    looks_like_test_failure,
    prune_tool_observation,
    summarize_test_observation,
)
from backend.app.llm.messages import Conversation, Message
from backend.app.persistence.context_repository import ContextRepository
from backend.app.tools.result import ToolResult

#上下文管理器：把各种context装配起来，给模型看。并且做压缩、更新状态，实现agentloop看到的接口

@runtime_checkable
class ContextManager(Protocol):
    """AgentLoop 可见的最小接口。"""

    def build_context(
        self,
        conversation: Conversation,
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> Conversation:
        """构造发给模型的视图；不得破坏 durable conversation 的持久化语义。"""
        ...

    def prune_observation(self, observation: str, *, tool_name: str | None = None) -> str:
        ...

    def update_after_tool(
        self,
        *,
        tool_name: str,
        tool_call_id: str,
        arguments: dict[str, Any] | None,
        result: ToolResult,
        observation: str,
    ) -> None:
        ...

    def update_after_user(self, content: str) -> None:
        ...

    def update_after_assistant(self, content: str | None) -> None:
        ...


@dataclass
class AssembledParts:
    system: str = ""
    project_rules: str = ""
    task: str = ""
    plan: str = ""
    memory: str = ""
    retrieved: str = ""
    git_context: str = ""
    lsp_context: str = ""
    workspace: str = ""
    checkpoint: str = ""
    recent: list[Message] = field(default_factory=list)
    section_tokens: list[ContextSectionUsage] = field(default_factory=list)
    total_tokens: int = 0
    compacted: bool = False
    retained_tail: int = 0


class DefaultContextManager:
    """分层、可追溯的 Context 管理实现。"""

    def __init__(
        self,
        *,
        session_id: str,
        workspace_root: str,
        budget: ContextBudget,
        repository: ContextRepository | None = None,
        model_id: str | None = None,
        tool_output_policy: ToolOutputPolicy | None = None,
        recent_tail_messages: int = 24,
        persist: bool = True,
        planner: Any | None = None,
        on_retrieve: Any | None = None,
        event_emitter: Any | None = None,
        git_context_provider: Any | None = None,
        lsp_context_provider: Any | None = None,
    ) -> None:
        self.session_id = session_id
        self.workspace_root = workspace_root
        self.budget = budget
        self.repository = repository
        self.model_id = model_id
        self.tool_output_policy = tool_output_policy or DEFAULT_TOOL_OUTPUT_POLICY
        self.recent_tail_messages = max(4, recent_tail_messages)
        self.persist = persist and repository is not None
        self._planner = planner
        self._on_retrieve = on_retrieve
        self._event_emitter = event_emitter
        self._git_context_provider = git_context_provider
        self._lsp_context_provider = lsp_context_provider

        self.project_rules = ProjectInstructionSet()
        self.task: TaskState | None = None
        self.plan: Plan | None = None
        self.memories: list[MemoryItem] = []
        self.retrieved: list[Any] = []
        self.latest_checkpoint: ContextCheckpoint | None = None
        self._extractor = MemoryCandidateExtractor()
        self._last_status: ContextStatus | None = None
        self._compaction_count = 0
        self._loaded = False

    def set_event_emitter(self, emitter: Any | None) -> None:
        """由 AgentService 注入；CLI/Web 经 AgentEventSink 消费。"""
        self._event_emitter = emitter

    def _emit(self, event: Any) -> None:
        if self._event_emitter is None or event is None:
            return
        try:
            self._event_emitter(event)
        except Exception:  # noqa: BLE001 — UI 失败不得阻断 Agent
            pass

    # ── lifecycle ──────────────────────────────────────────────

    def load(self) -> None:
        """从 SQLite 恢复 durable 状态。"""
        if self.repository is None:
            self._loaded = True
            return
        self.task = self.repository.get_active_task(self.session_id)
        self.plan = self.repository.get_latest_plan(self.session_id)
        self.memories = self.repository.list_memories(self.session_id)
        self.latest_checkpoint = self.repository.get_latest_checkpoint(self.session_id)
        self._loaded = True

    def ensure_loaded(self) -> None:
        if not self._loaded:
            self.load()

    def begin_run(self, user_goal: str, *, agent_run_id: str | None = None) -> None:
        """新一轮用户任务：确保 Task/Plan 存在。"""
        self.ensure_loaded()
        goal = (user_goal or "").strip()
        if not goal:
            return

        if self.task is None or not self.task.is_active:
            self.task = TaskState.create(session_id=self.session_id, goal=goal)
            self.task.next_actions = ["探索相关代码", "制定修改方案", "验证结果"]
            self._save_task()
        elif goal and goal != self.task.goal and len(goal) > 20:
            self.task.goal = goal
            self.task.current_focus = "理解新任务"
            self.task.status = TaskStatus.ACTIVE
            self.task.touch()
            self._save_task()

        self.refresh_project_rules(focus_path=None)
        self.refresh_retrieval(goal)
        self.refresh_git_context()
        self.refresh_lsp_context()

        need_plan = self.plan is None or self.plan.status in {
            PlanStatus.COMPLETED,
            PlanStatus.FAILED,
            PlanStatus.CANCELLED,
        }
        if need_plan:
            self.plan = self._create_plan(goal, agent_run_id=agent_run_id)
        else:
            if agent_run_id and self.plan.agent_run_id is None:
                self.plan.agent_run_id = agent_run_id
                self._save_plan()
            # 复用已有 Plan 时也要推一次快照，否则 CLI/Web 本轮收不到 plan_*
            self._emit_plan_lifecycle_created(self.plan)

    def set_retrieved(self, items: list[Any]) -> None:
        self.retrieved = list(items or [])

    def refresh_retrieval(self, query: str) -> None:
        if self._on_retrieve is None:
            return
        try:
            items = self._on_retrieve(query)
            if items:
                self.retrieved = list(items)
        except Exception:  # noqa: BLE001
            pass

    def refresh_git_context(self) -> None:
        if self._git_context_provider is None:
            return
        try:
            self._git_context_provider.refresh()
        except Exception:  # noqa: BLE001
            pass

    def refresh_lsp_context(self, *, focus_path: str | None = None) -> None:
        if self._lsp_context_provider is None:
            return
        try:
            if focus_path and hasattr(self._lsp_context_provider, "set_focus_path"):
                self._lsp_context_provider.set_focus_path(focus_path)
            self._lsp_context_provider.refresh()
        except Exception:  # noqa: BLE001
            pass

    def _create_plan(self, goal: str, *, agent_run_id: str | None) -> Plan:
        memories_text = "\n".join(
            m.render_line() for m in self.memories if not m.invalidated
        )[:3000]
        retrieved_text = "\n\n".join(
            getattr(r, "render", lambda: str(r))() for r in self.retrieved[:6]
        )[:4000]
        rules = self.project_rules.render()
        if self._planner is not None:
            try:
                plan = self._planner.create_initial_plan(
                    session_id=self.session_id,
                    goal=goal,
                    agent_run_id=agent_run_id,
                    project_rules=rules,
                    retrieved=retrieved_text,
                    memories=memories_text,
                )
                self._save_plan_obj(plan)
                self._emit_plan_lifecycle_created(plan)
                return plan
            except Exception:  # noqa: BLE001
                pass
        steps = _heuristic_plan_steps(goal)
        plan = Plan.create(
            session_id=self.session_id,
            goal=goal,
            agent_run_id=agent_run_id,
            step_titles=steps,
        )
        self._save_plan_obj(plan)
        self._emit_plan_lifecycle_created(plan)
        return plan

    def _emit_plan_lifecycle_created(self, plan: Plan) -> None:
        self._emit(plan_created_event(plan))
        for step in sorted(plan.steps, key=lambda s: s.step_index):
            if step.status == PlanStepStatus.IN_PROGRESS:
                self._emit(
                    plan_step_event(PLAN_STEP_STARTED, plan, step)
                )
                break

    def _set_step_status(
        self,
        step: PlanStep,
        status: PlanStepStatus,
        *,
        reason: str | None = None,
        emit: bool = True,
    ) -> None:
        if step.status == status:
            return
        step.status = status
        if not emit or self.plan is None:
            return
        et = event_type_for_step_status(status)
        if et is None:
            return
        self._emit(plan_step_event(et, self.plan, step, reason=reason))

    def _mark_plan_completed(self) -> None:
        if self.plan is None:
            return
        if self.plan.status == PlanStatus.COMPLETED:
            return
        self.plan.status = PlanStatus.COMPLETED
        if self.task:
            self.task.status = TaskStatus.COMPLETED
            self._save_task()
        self._emit(plan_completed_event(self.plan))

    def _save_plan_obj(self, plan: Plan) -> None:
        self.plan = plan
        if self.persist and self.repository is not None:
            self.repository.save_plan(plan)

    def refresh_project_rules(self, *, focus_path: str | None) -> None:
        discovered = discover_project_rules(self.workspace_root, focus_path=focus_path)
        merge_rules(self.project_rules, discovered)

    # ── Protocol ───────────────────────────────────────────────

    def build_context(
        self,
        conversation: Conversation,
        *,
        tools: list[dict[str, Any]] | None = None,
    ) -> Conversation:
        self.ensure_loaded()
        assembled = self._assemble(conversation, tools=tools)
        view = Conversation()
        # P0 system：保留原始 system + 分层注入（不得丢弃）
        hierarchical = self._join_hierarchical(assembled)
        system_msgs = [m for m in conversation.messages if m.role == "system"]
        if system_msgs:
            # 第一条 system 保留；额外注入分层块
            view.messages.append(system_msgs[0])
            if hierarchical:
                view.add_system(hierarchical)
            for extra in system_msgs[1:]:
                # 避免把旧的分层 system 重复塞入：跳过我们注入风格的块
                if extra.content and extra.content.lstrip().startswith("## "):
                    continue
                view.messages.append(extra)
        elif hierarchical:
            view.add_system(hierarchical)

        for msg in assembled.recent:
            view.messages.append(msg)

        self._last_status = ContextStatus(
            budget=self.budget.to_dict(),
            sections=assembled.section_tokens,
            total_tokens=assembled.total_tokens,
            compaction={
                "compacted": assembled.compacted,
                "count": self._compaction_count,
                "retained_tail": assembled.retained_tail,
                "last_checkpoint_id": (
                    self.latest_checkpoint.checkpoint_id if self.latest_checkpoint else None
                ),
                "last_checkpoint_at": (
                    self.latest_checkpoint.created_at if self.latest_checkpoint else None
                ),
            },
        )
        return view

    def prune_observation(self, observation: str, *, tool_name: str | None = None) -> str:
        return prune_tool_observation(
            observation,
            tool_name=tool_name,
            policy=self.tool_output_policy,
        )

    def update_after_user(self, content: str) -> None:
        self.ensure_loaded()
        try:
            for item in candidates_to_items(
                self.session_id,
                self._extractor.extract_from_user(content),
            ):
                self._add_memory(item)
        except Exception:  # noqa: BLE001 — extraction 失败不得拖垮 Loop
            pass

    def update_after_assistant(self, content: str | None) -> None:
        if not content:
            return
        self.ensure_loaded()
        try:
            for item in candidates_to_items(
                self.session_id,
                self._extractor.extract_from_agent(content),
            ):
                self._add_memory(item)
        except Exception:  # noqa: BLE001
            pass
        if self.task:
            # 最终回答时轻量收尾
            if "完成" in content or "fixed" in content.lower() or "通过" in content:
                if self.task.blockers:
                    self.task.blockers = [
                        b for b in self.task.blockers if "test" not in b.lower()
                    ]
                self.task.touch()
                self._save_task()
        if self.plan:
            self._complete_remaining_plan_steps()

    def update_after_tool(
        self,
        *,
        tool_name: str,
        tool_call_id: str,
        arguments: dict[str, Any] | None,
        result: ToolResult,
        observation: str,
    ) -> None:
        self.ensure_loaded()
        args = arguments or {}
        paths = extract_paths_from_tool_payload(args)
        paths.extend(extract_paths_from_tool_payload(result.to_dict()))
        paths = list(dict.fromkeys(paths))

        if paths:
            self.refresh_project_rules(focus_path=paths[0])

        ws = self._workspace()
        name = (tool_name or "").strip()

        if name in {"edit_file", "write_file"} and paths:
            for p in paths:
                ws.mark_modified(p)
            if self.task:
                self.task.current_focus = f"修改 {paths[0]}"
                note = f"编辑 {paths[0]}"
                if note not in self.task.completed_items:
                    self.task.completed_items.append(note)
                # Plan 推进只允许 complete_plan_step / 最终回答，不再按工具类型猜测
            self.refresh_lsp_context(focus_path=paths[0])
        elif name == "read_file" and paths:
            for p in paths:
                if p not in ws.active_files:
                    ws.active_files.append(p)
                if p not in ws.important_files and len(ws.important_files) < 30:
                    ws.important_files.append(p)
        elif name in {"search_code", "list_files"}:
            if name == "list_files":
                hint = summarize_test_observation(observation, max_len=120)
                if hint and hint not in ws.workspace_structure:
                    ws.workspace_structure.append(hint)
                    ws.workspace_structure = ws.workspace_structure[-15:]
        elif name == "run_command":
            failed = (not result.success) or looks_like_test_failure(observation)
            summary = summarize_test_observation(observation)
            # 仅当命令输出像测试/构建时记入 test_results
            cmd = str(args.get("command") or args.get("cmd") or "")
            if _looks_like_verification(cmd, observation):
                ws.record_test(summary, failed=failed)
                if self.task:
                    if failed:
                        blocker = f"验证失败: {summary[:160]}"
                        if blocker not in self.task.blockers:
                            self.task.blockers.append(blocker)
                        self.task.status = TaskStatus.BLOCKED
                        self.task.current_focus = "修复验证失败"
                    else:
                        self.task.blockers = [
                            b for b in self.task.blockers if not b.startswith("验证失败")
                        ]
                        if self.task.status == TaskStatus.BLOCKED:
                            self.task.status = TaskStatus.ACTIVE
                        done = f"验证通过: {summary[:120]}"
                        if done not in self.task.completed_items:
                            self.task.completed_items.append(done)
        elif name == "complete_plan_step":
            # 完成动作在工具 execute 里已调用 complete_current_step；此处不再重复
            pass
        elif name.startswith("git_"):
            self.refresh_git_context()
        elif name.startswith("lsp_"):
            focus = None
            if paths:
                focus = paths[0]
            elif isinstance(args.get("path"), str):
                focus = args["path"]
            self.refresh_lsp_context(focus_path=focus)

        if self.task:
            self.task.workspace_state = ws
            self.task.touch()
            self._save_task()

        try:
            for item in candidates_to_items(
                self.session_id,
                self._extractor.extract_from_tool(
                    observation,
                    source_id=tool_call_id,
                    file_path=paths[0] if paths else None,
                ),
            ):
                self._add_memory(item)
        except Exception:  # noqa: BLE001
            pass

        # 不在每次工具 observation 上调用 LLM replan：
        # 模型常把 6 步清单缩成 1 步并把当前步标 failed，破坏 CLI 进度。
        # 步骤推进只走 _advance_plan_on_*。

    # ── compaction / status / invalidate ───────────────────────

    def compact(
        self,
        conversation: Conversation,
        *,
        trigger: CheckpointTrigger = CheckpointTrigger.MANUAL,
    ) -> ContextCheckpoint:
        """手动/自动压缩：写 Checkpoint；不删除 SQLite messages。"""
        self.ensure_loaded()
        summary = self._build_checkpoint_summary(conversation)
        # boundary：保留尾部消息数（相对当前 conversation 长度）
        boundary = max(0, len(conversation.messages) - self.recent_tail_messages)
        ckpt = ContextCheckpoint.create(
            session_id=self.session_id,
            trigger=trigger,
            summary=summary,
            retained_message_boundary=boundary,
            model_id=self.model_id,
        )
        self.latest_checkpoint = ckpt
        self._compaction_count += 1
        if self.persist and self.repository is not None:
            self.repository.save_checkpoint(ckpt)
        return ckpt

    def invalidate_after_revert(self, *, paths: list[str] | None = None) -> None:
        self.ensure_loaded()
        ws = self._workspace()
        ws.invalidate(paths=paths)
        if self.task:
            self.task.workspace_state = ws
            self.task.current_focus = "工作区已 revert，需重新读取相关文件"
            note = "workspace reverted — prior file facts may be stale"
            if note not in self.task.blockers:
                self.task.blockers.append(note)
            self.task.touch()
            self._save_task()
        if self.persist and self.repository is not None:
            if paths:
                self.repository.invalidate_memories_for_paths(self.session_id, paths)
            else:
                self.repository.invalidate_workspace_facts(self.session_id)
            self.memories = self.repository.list_memories(self.session_id)
        else:
            for mem in self.memories:
                if paths:
                    if mem.file_path in paths:
                        mem.invalidated = True
                elif mem.file_path or mem.category.value in {
                    "architecture",
                    "important_fact",
                }:
                    mem.invalidated = True

        # 规则文件也可能被改回
        if paths:
            for p in paths:
                if p.endswith("AGENTS.md") or p.endswith("CLAUDE.md"):
                    self.project_rules.invalidate(p)
            self.refresh_project_rules(focus_path=paths[0] if paths else None)
        self.refresh_git_context()
        self.refresh_lsp_context()

    def status(self, conversation: Conversation | None = None) -> ContextStatus:
        self.ensure_loaded()
        if conversation is not None:
            self.build_context(conversation, tools=None)
        if self._last_status is not None:
            return self._last_status
        return ContextStatus(
            budget=self.budget.to_dict(),
            sections=[],
            total_tokens=0,
            compaction={"count": self._compaction_count},
        )

    # ── assembly internals ─────────────────────────────────────

    def _assemble(
        self,
        conversation: Conversation,
        *,
        tools: list[dict[str, Any]] | None,
    ) -> AssembledParts:
        parts = AssembledParts()
        budget = self.budget
        tools_tokens = budget.estimate_tools(tools)

        system_text = ""
        for m in conversation.messages:
            if m.role == "system" and m.content and not m.content.lstrip().startswith("## "):
                system_text = m.content
                break
        parts.system = system_text
        parts.project_rules = self.project_rules.render()
        parts.task = self.task.render() if self.task else ""
        parts.plan = self.plan.render() if self.plan else ""
        active_memories = [m for m in self.memories if not m.invalidated]
        if active_memories:
            mem_lines = ["## Durable Memory"]
            mem_lines.extend(m.render_line() for m in active_memories[:40])
            parts.memory = "\n".join(mem_lines)
        parts.workspace = self._workspace().render()
        if self._git_context_provider is not None:
            parts.git_context = (
                self._git_context_provider.cached
                or self._git_context_provider.build_workspace_context()
            )
        if self._lsp_context_provider is not None:
            parts.lsp_context = (
                self._lsp_context_provider.cached
                or self._lsp_context_provider.build_workspace_context()
            )
        if self.latest_checkpoint:
            parts.checkpoint = self.latest_checkpoint.render()
        if self.retrieved:
            lines = ["## Retrieved Context"]
            for item in self.retrieved[:8]:
                render = getattr(item, "render", None)
                lines.append(render() if callable(render) else str(item))
            parts.retrieved = "\n\n".join(lines)

        # 非 system 消息作为 recent 候选
        non_system = [m for m in conversation.messages if m.role != "system"]
        # tool 内容再裁剪一遍（视图层）
        recent_candidates = [_maybe_prune_message(m, self.tool_output_policy) for m in non_system]

        def tok(text: str) -> int:
            return budget.estimate(text)

        section_defs: list[tuple[str, str, ContextPriority]] = [
            ("System", parts.system, ContextPriority.P0),
            ("Project Rules", parts.project_rules, ContextPriority.P1),
            ("Task State", parts.task, ContextPriority.P1),
            ("Plan", parts.plan, ContextPriority.P1),
            ("Durable Memory", parts.memory, ContextPriority.P1),
            ("Retrieved Context", parts.retrieved, ContextPriority.P2),
            ("Git Context", parts.git_context, ContextPriority.P2),
            ("LSP Context", parts.lsp_context, ContextPriority.P2),
            ("Workspace State", parts.workspace, ContextPriority.P2),
            ("Checkpoint", parts.checkpoint, ContextPriority.P2),
        ]

        used = tools_tokens
        for name, text, pri in section_defs:
            t = tok(text) if text else 0
            parts.section_tokens.append(ContextSectionUsage(name, t, pri))
            used += t

        # 先尝试全量 recent；超预算则 checkpoint + tail
        recent_tokens = sum(budget.estimate_message(m) for m in recent_candidates)
        usable = budget.usable_budget

        if used + recent_tokens <= usable:
            parts.recent = recent_candidates
            parts.retained_tail = len(recent_candidates)
        else:
            # 需要压缩
            parts.compacted = True
            if self.latest_checkpoint is None or _should_refresh_checkpoint(
                self.latest_checkpoint, len(conversation.messages)
            ):
                self.compact(conversation, trigger=CheckpointTrigger.AUTOMATIC)
                parts.checkpoint = (
                    self.latest_checkpoint.render() if self.latest_checkpoint else parts.checkpoint
                )
                # 刷新 checkpoint section token
                for i, sec in enumerate(parts.section_tokens):
                    if sec.name == "Checkpoint":
                        parts.section_tokens[i] = ContextSectionUsage(
                            "Checkpoint",
                            tok(parts.checkpoint),
                            ContextPriority.P2,
                        )
                        break
                used = tools_tokens + sum(s.tokens for s in parts.section_tokens)

            # 从尾部保留消息直到预算耗尽；优先丢弃更旧的 P4/P3
            tail: list[Message] = []
            remaining = max(0, usable - used)
            for msg in reversed(recent_candidates):
                cost = budget.estimate_message(msg)
                if cost > remaining and tail:
                    break
                if cost > remaining and not tail:
                    # 单条过大：再裁剪 tool
                    if msg.role == "tool" and msg.content:
                        pruned = prune_tool_observation(
                            msg.content,
                            tool_name="tool",
                            policy=ToolOutputPolicy(max_chars=2000, max_lines=60),
                        )
                        msg = Message(
                            role=msg.role,
                            content=pruned,
                            tool_calls=msg.tool_calls,
                            tool_call_id=msg.tool_call_id,
                        )
                        cost = budget.estimate_message(msg)
                    if cost > remaining:
                        break
                tail.append(msg)
                remaining -= cost
            tail.reverse()
            # 保证 tool 调用链完整：若截断点落在 tool 中间，向前补齐
            parts.recent = _repair_tool_call_chain(recent_candidates, tail)
            parts.retained_tail = len(parts.recent)

        recent_tok = sum(budget.estimate_message(m) for m in parts.recent)
        tool_out_est = sum(
            budget.estimate_message(m) for m in parts.recent if m.role == "tool"
        )
        parts.section_tokens.append(
            ContextSectionUsage("Recent Context", recent_tok - tool_out_est, ContextPriority.P3)
        )
        parts.section_tokens.append(
            ContextSectionUsage("Tool Output", tool_out_est, ContextPriority.P3)
        )
        parts.total_tokens = used + recent_tok
        return parts

    def _join_hierarchical(self, parts: AssembledParts) -> str:
        blocks = [
            parts.project_rules,
            parts.task,
            parts.plan,
            parts.memory,
            parts.retrieved,
            parts.git_context,
            parts.lsp_context,
            parts.workspace,
            parts.checkpoint,
        ]
        return "\n\n".join(b for b in blocks if b and b.strip())

    def _workspace(self) -> WorkspaceState:
        if self.task:
            return self.task.workspace_state
        return WorkspaceState()

    def _build_checkpoint_summary(self, conversation: Conversation) -> dict[str, Any]:
        task = self.task
        ws = self._workspace()
        return {
            "objective": task.goal if task else "",
            "current_status": task.status.value if task else "unknown",
            "completed_work": list(task.completed_items[-12:]) if task else [],
            "active_work": [task.current_focus] if task and task.current_focus else [],
            "blockers": list(task.blockers[-8:]) if task else [],
            "important_decisions": list(task.important_decisions[-8:]) if task else [],
            "important_files": list(ws.important_files[-12:] + ws.modified_files[-12:]),
            "recent_test_results": list(ws.test_results[-6:]),
            "next_actions": list(task.next_actions[-8:]) if task else [],
            "message_count": len(conversation.messages),
        }

    def _add_memory(self, item: MemoryItem) -> None:
        # 去重：相同 content 跳过
        for existing in self.memories:
            if not existing.invalidated and existing.content == item.content:
                return
        self.memories.append(item)
        if self.persist and self.repository is not None:
            self.repository.save_memory(item)
        if self.task and item.category.value == "decision":
            if item.content not in self.task.important_decisions:
                self.task.important_decisions.append(item.content)
                self._save_task()

    def _save_task(self) -> None:
        if self.persist and self.repository is not None and self.task is not None:
            self.repository.upsert_task(self.task)

    def _save_plan(self) -> None:
        if self.persist and self.repository is not None and self.plan is not None:
            self.repository.save_plan(self.plan)

    def _current_in_progress_step(self):
        if not self.plan:
            return None
        for step in sorted(self.plan.steps, key=lambda s: s.step_index):
            if step.status == PlanStepStatus.IN_PROGRESS:
                return step
        return None

    def complete_current_step(self, *, note: str = "") -> dict:
        """显式完成当前 Plan 条目，并激活下一条（用户期望的逐步信号）。"""
        self.ensure_loaded()
        if not self.plan or self.plan.status == PlanStatus.COMPLETED:
            return {"ok": False, "error": "no active plan"}
        step = self._current_in_progress_step()
        if step is None:
            return {"ok": False, "error": "no in_progress plan step"}
        reason = note.strip() or None
        self._set_step_status(step, PlanStepStatus.COMPLETED, reason=reason)
        if self.task:
            done = f"完成步骤: {step.title}"
            if done not in self.task.completed_items:
                self.task.completed_items.append(done)
            self.task.touch()
            self._save_task()
        self._activate_next_plan_step()
        self._save_plan()
        nxt = self._current_in_progress_step()
        return {
            "ok": True,
            "completed_step_index": step.step_index,
            "completed_step": step.title,
            "next_step_index": nxt.step_index if nxt else None,
            "next_step": nxt.title if nxt else None,
            "plan_completed": self.plan.status == PlanStatus.COMPLETED,
        }

    def _complete_remaining_plan_steps(self) -> None:
        """最终回答时收尾：未完成步骤标 completed，发 plan_completed。"""
        if not self.plan or self.plan.status == PlanStatus.COMPLETED:
            return
        for step in sorted(self.plan.steps, key=lambda s: s.step_index):
            if step.status in {PlanStepStatus.PENDING, PlanStepStatus.IN_PROGRESS}:
                self._set_step_status(step, PlanStepStatus.COMPLETED)
        self._mark_plan_completed()
        self._save_plan()

    def _activate_next_plan_step(self) -> None:
        if not self.plan:
            return
        for step in sorted(self.plan.steps, key=lambda s: s.step_index):
            if step.status == PlanStepStatus.PENDING:
                self._set_step_status(step, PlanStepStatus.IN_PROGRESS)
                if self.task:
                    self.task.current_focus = step.title
                    self.task.next_actions = [step.title] + [
                        s.title
                        for s in self.plan.steps
                        if s.status == PlanStepStatus.PENDING
                    ][:5]
                return
        # 无更多 PENDING：若均已完成/跳过则收尾
        if all(
            s.status in {PlanStepStatus.COMPLETED, PlanStepStatus.SKIPPED}
            for s in self.plan.steps
        ):
            self._mark_plan_completed()


def _heuristic_plan_steps(goal: str) -> list[str]:
    g = goal.lower()
    steps = ["探索相关代码与项目规则", "定位问题根因", "实施代码修改", "运行验证并修复失败"]
    if any(k in g for k in ("重构", "refactor")):
        steps = ["阅读现有结构与 AGENTS.md", "制定重构边界", "分步修改并保持 API 兼容", "运行测试套件"]
    elif any(k in g for k in ("测试", "test")):
        steps = ["定位失败测试", "修复实现或测试", "重新运行验证"]
    return steps


def _looks_like_verification(command: str, observation: str) -> bool:
    blob = f"{command}\n{observation}".lower()
    keys = (
        "test",
        "pytest",
        "jest",
        "mocha",
        "phpunit",
        "cargo test",
        "mvn test",
        "go test",
        "npm test",
        "failure",
        "passed",
        "failed",
        "assert",
    )
    return any(k in blob for k in keys)


def _maybe_prune_message(msg: Message, policy: ToolOutputPolicy) -> Message:
    if msg.role != "tool" or not msg.content:
        return msg
    pruned = prune_tool_observation(msg.content, tool_name="tool", policy=policy)
    if pruned == msg.content:
        return msg
    return Message(
        role=msg.role,
        content=pruned,
        tool_calls=msg.tool_calls,
        tool_call_id=msg.tool_call_id,
        message_id=msg.message_id,
        session_id=msg.session_id,
        agent_run_id=msg.agent_run_id,
        step_id=msg.step_id,
        seq=msg.seq,
        created_at=msg.created_at,
    )


def _should_refresh_checkpoint(ckpt: ContextCheckpoint, message_count: int) -> bool:
    boundary = ckpt.retained_message_boundary or 0
    return message_count - boundary > 16


def _repair_tool_call_chain(full: list[Message], tail: list[Message]) -> list[Message]:
    if not tail:
        return tail
    start_idx = 0
    # 找到 tail[0] 在 full 中的位置
    for i, m in enumerate(full):
        if m is tail[0] or (
            m.role == tail[0].role
            and m.content == tail[0].content
            and m.tool_call_id == tail[0].tool_call_id
        ):
            start_idx = i
            break
    # 若从 tool 消息开始，向前找到对应 assistant tool_calls
    while start_idx > 0 and full[start_idx].role == "tool":
        start_idx -= 1
    if start_idx < len(full) and full[start_idx].role == "assistant" and full[start_idx].tool_calls:
        return full[start_idx:]
    return tail
