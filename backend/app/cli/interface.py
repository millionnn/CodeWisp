"""CodeWisp 命令行界面（V0.8）。

```text
CLI → AgentService / SessionService → PermissionHandler / EventSink → AgentLoop
```

CLI 只做输入、命令解析、交互授权与实时 AgentEvent 展示；不实现 Agent Core、不直连 SQLite。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from backend.app.agent.state import AgentStatus
from backend.app.banner import print_app_banner
from backend.app.cli.event_sink import CliEventSink
from backend.app.cli.help_text import HELP_TEXT, HELP_TEXT_PLAIN
from backend.app.cli.prompt import read_line
from backend.app.cli.render_diff import render_file_diffs
from backend.app.cli.render_md import render_markdown
from backend.app.cli.select import select_option
from backend.app.cli.status_bar import (
    DEFAULT_SESSION_TITLES,
    StatusBarState,
    summarize_session_title,
)
from backend.app.cli.theme import get_theme, make_console
from backend.app.cli.trace import render_agent_trace, render_run_summary
from backend.app.changes.errors import RevertError
from backend.app.llm.errors import CodeWispError
from backend.app.permissions.cli import CliPermissionHandler
from backend.app.providers.defaults import DEFAULT_MODEL_ID, DEFAULT_PROVIDER_ID
from backend.app.providers.errors import ModelError, ProviderError
from backend.app.services.agent_service import AgentService
from backend.app.session.errors import SessionError, SessionNotFoundError
from backend.app.session.models import Session
from backend.app.tools.factory import create_default_registry
from backend.app.workspace.workspace import Workspace

EXIT_COMMANDS = frozenset({"/exit", "/quit", "exit", "quit"})
DELETE_COMMANDS = frozenset({"/delete", "/rm"})


def print_banner(
    *,
    workspace_root: Path | None = None,
    session: Session | None = None,
    output_fn: Callable[[str], None] = print,
) -> None:
    print_app_banner(output_fn=output_fn)
    if workspace_root is not None:
        output_fn(f"  Workspace : {workspace_root}")
    if session is not None:
        output_fn(f"  Session   : {session.session_id} ({session.title})")
        output_fn(f"  Model     : {session.provider_id}/{session.model_id}")
    output_fn("")
    output_fn("  Commands  : /help  /sessions  /session  /new  /use  /history")
    output_fn("              /providers  /models  /model  /diff  /revert")
    output_fn("              /context  /plan  /memory  /status  /delete  /exit")
    output_fn("  Type a task to continue the current Session.\n")


def read_user_input(
    prompt: str = "> ",
    *,
    bottom_toolbar=None,
) -> str | None:
    """从标准输入读取一行（prompt_toolkit：正确处理中文退格/方向键）。"""
    return read_line(prompt, bottom_toolbar=bottom_toolbar)


def _print_run_result(
    result: object,
    *,
    output_fn: Callable[[str], None],
    show_tool_trace: bool,
    live_trace: bool = False,
    answer_already_streamed: bool = False,
) -> None:
    from backend.app.services.agent_service import AgentRunResult

    assert isinstance(result, AgentRunResult)
    state = result.state

    if show_tool_trace and not live_trace:
        render_agent_trace(state, result.run, output_fn=output_fn)
    elif live_trace:
        render_run_summary(state, result.run, output_fn=output_fn)

    if state.status == AgentStatus.COMPLETED:
        if not answer_already_streamed:
            if output_fn is print and get_theme().rich_enabled:
                render_markdown(state.final_answer or "")
            elif output_fn is print:
                output_fn(f"\nCodeWisp:\n{state.final_answer}\n")
            else:
                output_fn("\nCodeWisp:")
                render_markdown(
                    state.final_answer or "",
                    output_fn=output_fn,
                    force_plain=True,
                )
    elif state.status == AgentStatus.MAX_STEPS:
        output_fn("\nCodeWisp:\n（已达最大步数 / 迭代预算耗尽）")
        if state.error:
            output_fn(state.error)
        if state.final_answer and not answer_already_streamed:
            output_fn(state.final_answer)
        output_fn("")
    elif state.status == AgentStatus.PERMISSION_REQUIRED:
        output_fn("\nCodeWisp:\n（需要用户授权，已停止自动继续）")
        if state.error:
            output_fn(state.error)
        if state.final_answer and not answer_already_streamed:
            output_fn(state.final_answer)
        output_fn("")
    elif state.status == AgentStatus.FAILED:
        output_fn(f"错误：{state.error}")
    else:
        output_fn(f"错误：意外状态 {state.status}")


def _session_has_dialogue(agents: AgentService, session_id: str) -> bool:
    return bool(agents.sessions.list_runs(session_id))


def _discard_unused_session(
    agents: AgentService,
    session: Session,
    *,
    output_fn: Callable[[str], None] | None = None,
) -> bool:
    if _session_has_dialogue(agents, session.session_id):
        return False
    try:
        agents.sessions.delete_session(session.session_id)
    except SessionError:
        return False
    if output_fn is not None:
        output_fn(f"（已丢弃未使用的空 Session: {session.session_id}）")
    return True


def _parse_new_args(rest: str) -> tuple[str, str | None, str | None]:
    """解析 ``/new`` 参数 → (title, provider_id|None, model_id|None)。"""
    tokens = rest.split()
    provider_id: str | None = None
    model_id: str | None = None
    title_parts: list[str] = []
    i = 0
    while i < len(tokens):
        tok = tokens[i]
        if tok == "--provider-id" and i + 1 < len(tokens):
            provider_id = tokens[i + 1]
            i += 2
            continue
        if tok in {"--model-id", "--model"} and i + 1 < len(tokens):
            model_id = tokens[i + 1]
            i += 2
            continue
        title_parts.append(tok)
        i += 1
    title = " ".join(title_parts).strip() or "CLI Session"
    return title, provider_id, model_id


def run_cli(
    agents: AgentService,
    *,
    workspace_root: Path,
    session_id: str | None = None,
    session_title: str = "CLI Session",
    provider_id: str = DEFAULT_PROVIDER_ID,
    model_id: str = DEFAULT_MODEL_ID,
    input_fn: Callable[[str], str | None] = read_user_input,
    output_fn: Callable[[str], None] = print,
    show_tool_trace: bool = False,
) -> int:
    """交互式入口：命令经 Service；任务经 AgentService.run。"""
    try:
        if session_id:
            current = agents.sessions.get_session(session_id)
        else:
            current = agents.sessions.create_session(
                title=session_title,
                workspace=workspace_root,
                provider_id=provider_id,
                model_id=model_id,
            )
    except SessionError as exc:
        output_fn(f"Session 错误：{exc}")
        return 1

    print_banner(
        workspace_root=Path(current.workspace),
        session=current,
        output_fn=output_fn,
    )

    # 仅测试注入的 input_fn 走编号/y-n；真实 TTY 用方向键 + prompt_toolkit
    select_input = None if input_fn is read_user_input else input_fn

    # V0.8：交互授权 + 实时 EventSink（CLI 实现；AgentLoop 不感知 UI）
    permission_handler = CliPermissionHandler(
        input_fn=select_input,
        output_fn=output_fn,
    )
    status_bar = StatusBarState()
    status_bar.update_workspace(workspace_root)
    status_bar.update_from_session(current)

    def _plan_provider():
        try:
            return agents.get_latest_plan(current.session_id)
        except Exception:  # noqa: BLE001
            return None

    live_sink = CliEventSink(
        output_fn=output_fn,
        model_id=current.model_id,
        plan_provider=_plan_provider,
        show_todos=status_bar.show_todos,
        show_tool_trace=show_tool_trace,
    )

    def _prompt_toolbar() -> str:
        # OpenCode 风格 footer：左 workspace，右 title/model/tokens
        return status_bar.toolbar_text()

    while True:
        # 非 TTY / 测试：在提示前打印一行 footer；TTY 用 bottom_toolbar（不占对话区）
        use_toolbar = input_fn is read_user_input
        if not use_toolbar:
            status_bar.print_line(output_fn)
            user_text = input_fn("> ")
        else:
            user_text = read_user_input("> ", bottom_toolbar=_prompt_toolbar)
        if user_text is None:
            _discard_unused_session(agents, current, output_fn=output_fn)
            output_fn("再见。")
            return 0

        user_text = user_text.strip()
        if user_text == "":
            output_fn("（已忽略空输入）")
            continue

        lower = user_text.lower()
        if lower in EXIT_COMMANDS:
            _discard_unused_session(agents, current, output_fn=output_fn)
            output_fn("再见。")
            return 0

        if lower in {"/help", "help"}:
            if output_fn is print and get_theme().rich_enabled:
                make_console().print(HELP_TEXT)
            else:
                output_fn(HELP_TEXT_PLAIN)
            continue

        if lower == "/sessions":
            _cmd_sessions(agents, current, output_fn)
            continue

        if lower == "/session":
            _cmd_session(agents, current, output_fn)
            continue

        if lower == "/history":
            _cmd_history(agents, current.session_id, output_fn)
            continue

        if lower == "/providers":
            _cmd_providers(agents, current, output_fn)
            continue

        if lower == "/models":
            _cmd_models(agents, current, output_fn)
            continue

        if lower == "/status":
            _cmd_status(agents, current, output_fn)
            continue

        if lower == "/context" or lower.startswith("/context "):
            _cmd_context(agents, current, user_text, output_fn)
            continue

        if lower == "/plan" or lower.startswith("/plan "):
            _cmd_plan(agents, current, user_text, output_fn)
            continue

        if lower == "/memory" or lower.startswith("/memory "):
            _cmd_memory(agents, current, user_text, output_fn)
            continue

        if lower == "/diff" or lower.startswith("/diff "):
            _cmd_diff(
                agents,
                current,
                user_text,
                output_fn=output_fn,
                input_fn=select_input,
            )
            continue

        if lower == "/revert" or lower.startswith("/revert "):
            _cmd_revert(
                agents,
                current,
                user_text,
                output_fn=output_fn,
                input_fn=select_input,
                permission_handler=permission_handler,
                event_sink=live_sink,
            )
            continue

        if lower == "/model" or lower.startswith("/model "):
            current = _cmd_model(
                agents, current, user_text, output_fn, input_fn=select_input
            )
            live_sink.set_model_id(current.model_id)
            status_bar.update_from_session(current)
            continue

        if lower.startswith("/new"):
            rest = user_text[4:].strip()
            title, pid, mid = _parse_new_args(rest)
            new_provider = provider_id
            new_model = model_id
            try:
                if pid and mid:
                    agents.require_resolver().lookup(pid, mid)
                    new_provider, new_model = pid, mid
                elif mid and not pid:
                    new_provider, new_model = agents.parse_model_ref(
                        mid,
                        current_provider_id=current.provider_id,
                    )
                elif pid and not mid:
                    output_fn("用法: /new [--provider-id P --model-id M] [title]")
                    continue
            except (ProviderError, ModelError, CodeWispError) as exc:
                output_fn(f"✗ Model Error\n{exc}")
                continue

            _discard_unused_session(agents, current, output_fn=output_fn)
            try:
                current = agents.sessions.create_session(
                    title=title,
                    workspace=workspace_root,
                    provider_id=new_provider,
                    model_id=new_model,
                )
            except SessionError as exc:
                output_fn(f"错误：{exc}")
                continue
            live_sink.set_model_id(current.model_id)
            status_bar.update_from_session(current)
            status_bar.update_context(used=None, budget=None)
            output_fn(
                f"已创建 Session: {current.session_id} ({current.title})\n"
                f"Model: {current.provider_id}/{current.model_id}"
            )
            continue

        if lower.startswith("/use"):
            parts = user_text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                target_id = _pick_session(
                    agents,
                    current,
                    title="选择要切换的 Session",
                    output_fn=output_fn,
                    input_fn=select_input,
                    exclude_current=False,
                )
                if not target_id:
                    output_fn("已取消。")
                    continue
            else:
                target_id = parts[1].strip()
            if target_id == current.session_id:
                output_fn(f"已在当前 Session: {current.session_id}")
                continue
            try:
                nxt = agents.sessions.get_session(target_id)
            except SessionNotFoundError as exc:
                output_fn(f"错误：{exc}")
                continue
            _discard_unused_session(agents, current, output_fn=output_fn)
            current = nxt
            live_sink.set_model_id(current.model_id)
            status_bar.update_from_session(current)
            try:
                ctx = agents.get_context_status(current.session_id)
                status_bar.update_context(
                    used=ctx.total_tokens,
                    budget=int(ctx.budget.get("usable_budget") or 0) or None,
                )
            except Exception:  # noqa: BLE001
                status_bar.update_context(used=None, budget=None)
            output_fn(
                f"已切换到 Session: {current.session_id} ({current.title})\n"
                f"Model: {current.provider_id}/{current.model_id}\n"
                f"Workspace: {current.workspace}"
            )
            continue

        cmd_word = user_text.split(maxsplit=1)[0].lower()
        if cmd_word in DELETE_COMMANDS:
            parts = user_text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                target_id = _pick_session(
                    agents,
                    current,
                    title="选择要删除的 Session",
                    output_fn=output_fn,
                    input_fn=select_input,
                    exclude_current=False,
                )
                if not target_id:
                    output_fn("已取消。")
                    continue
            else:
                target_id = parts[1].strip()
            try:
                target = agents.sessions.get_session(target_id)
            except SessionNotFoundError as exc:
                output_fn(f"错误：{exc}")
                continue
            deleting_current = target.session_id == current.session_id
            try:
                agents.sessions.delete_session(target.session_id)
            except SessionError as exc:
                output_fn(f"错误：{exc}")
                continue
            output_fn(f"已删除 Session: {target.session_id} ({target.title})")
            if deleting_current:
                try:
                    current = agents.sessions.create_session(
                        title=session_title,
                        workspace=workspace_root,
                        provider_id=provider_id,
                        model_id=model_id,
                    )
                except SessionError as exc:
                    output_fn(f"错误：无法创建替代 Session：{exc}")
                    return 1
                live_sink.set_model_id(current.model_id)
                status_bar.update_from_session(current)
                status_bar.update_context(used=None, budget=None)
                output_fn(
                    f"已切换到新 Session: {current.session_id} ({current.title})"
                )
            continue

        if user_text.startswith("/"):
            output_fn("未知命令。输入 /help 查看可用命令。")
            continue

        live_sink.set_model_id(current.model_id)
        try:
            # 每轮任务重置实时 sink，避免跨 run 累加
            live_sink = CliEventSink(
                output_fn=output_fn,
                model_id=current.model_id,
                plan_provider=_plan_provider,
                show_todos=status_bar.show_todos,
                show_tool_trace=show_tool_trace,
            )
            # 未命名 Session：用首条用户消息摘要作为标题
            if current.title.strip() in DEFAULT_SESSION_TITLES:
                runs_before = agents.sessions.list_runs(current.session_id)
                if not runs_before:
                    try:
                        current = agents.sessions.rename_session(
                            current.session_id,
                            summarize_session_title(user_text),
                        )
                        status_bar.update_from_session(current)
                    except SessionError:
                        pass

            result = agents.run(
                current.session_id,
                user_text,
                event_sink=live_sink,
                permission_handler=permission_handler,
            )
            current = result.session
            status_bar.update_from_session(current)
            try:
                ctx = agents.get_context_status(current.session_id)
                status_bar.update_context(
                    used=ctx.total_tokens,
                    budget=int(ctx.budget.get("usable_budget") or 0) or None,
                )
            except Exception:  # noqa: BLE001
                pass
        except CodeWispError as exc:
            output_fn(f"错误：{exc}")
            continue

        _print_run_result(
            result,
            output_fn=output_fn,
            show_tool_trace=show_tool_trace,
            live_trace=show_tool_trace,
            answer_already_streamed=live_sink.answer_streamed,
        )

    return 0  # pragma: no cover


def _cmd_sessions(
    agents: AgentService,
    current: Session,
    output_fn: Callable[[str], None],
) -> None:
    items = agents.sessions.list_sessions()
    if not items:
        output_fn("（无 Session）")
        return
    output_fn("Sessions\n")
    for session in items:
        mark = ">" if session.session_id == current.session_id else " "
        output_fn(f"{mark} {session.session_id}   {session.title}")
        output_fn(f"          {session.provider_id} / {session.model_id}")
        output_fn(f"          {session.workspace}")
        output_fn("")


def _cmd_session(
    agents: AgentService,
    current: Session,
    output_fn: Callable[[str], None],
) -> None:
    resumed = agents.resume(current.session_id)
    output_fn("Session\n")
    output_fn(f"ID        : {current.session_id}")
    output_fn(f"Title     : {current.title}")
    output_fn(f"Workspace : {current.workspace}")
    output_fn("")
    output_fn(f"Provider  : {current.provider_id}")
    output_fn(f"Model     : {current.model_id}")
    output_fn("")
    output_fn(f"Status    : {current.status}")
    output_fn(f"Created   : {current.created_at or '—'}")
    output_fn(f"Updated   : {current.updated_at or '—'}")
    output_fn("")
    output_fn(f"Runs      : {resumed.run_count}")
    output_fn(f"Messages  : {resumed.message_count}")


def _cmd_history(
    agents: AgentService,
    session_id: str,
    output_fn: Callable[[str], None],
) -> None:
    resumed = agents.resume(session_id)
    visible = [
        msg
        for msg in resumed.conversation.messages
        if msg.role == "user"
        or (
            msg.role == "assistant"
            and (msg.content or "").strip()
            and not msg.tool_calls
        )
    ]

    output_fn(
        f"对话 {len(visible)} 条"
        f"（底层轨迹 {resumed.message_count} 条消息 / {resumed.run_count} 次 Run）"
    )
    if not visible:
        output_fn("（暂无用户与助手对话）")
        return

    use_rich = output_fn is print and get_theme().rich_enabled
    for msg in visible:
        if msg.role == "user":
            if use_rich:
                make_console().print(f"\n[cw.user]你[/]")
                make_console().print(msg.content or "", style="cw.dim")
            else:
                output_fn("\n[你]")
                output_fn(msg.content or "")
        else:
            if use_rich:
                make_console().print()
                render_markdown(msg.content or "")
            else:
                output_fn("\n[CodeWisp]")
                render_markdown(
                    msg.content or "",
                    output_fn=output_fn,
                    force_plain=True,
                )


def _cmd_providers(
    agents: AgentService,
    current: Session,
    output_fn: Callable[[str], None],
) -> None:
    try:
        providers = agents.list_providers()
        resolver = agents.require_resolver()
    except CodeWispError as exc:
        output_fn(f"✗ {exc}")
        return

    output_fn("Available Providers\n")
    for provider in providers:
        mark = ">" if provider.provider_id == current.provider_id else " "
        models = resolver.models.list_for_provider(provider.provider_id)
        status = (
            "configured"
            if resolver.is_credential_configured(provider.provider_id)
            else "registered"
        )
        output_fn(f"{mark} {provider.provider_id}")
        output_fn(f"    {provider.display_name}")
        output_fn(f"    status: {status}")
        output_fn(f"    models: {len(models)}")
        caps = ", ".join(sorted(provider.capabilities)) or "—"
        output_fn(f"    capabilities: {caps}")
        output_fn("")


def _cmd_models(
    agents: AgentService,
    current: Session,
    output_fn: Callable[[str], None],
) -> None:
    try:
        models = agents.list_models()
    except CodeWispError as exc:
        output_fn(f"✗ {exc}")
        return

    output_fn("Available Models\n")
    output_fn(f"{'Provider':<12} {'Model':<22} {'Current':<8} Display")
    output_fn("-" * 64)
    for model in models:
        is_current = (
            model.provider_id == current.provider_id
            and model.model_id == current.model_id
        )
        mark = "✓" if is_current else ""
        output_fn(
            f"{model.provider_id:<12} {model.model_id:<22} {mark:<8} {model.display_name}"
        )
    output_fn("")
    for model in models:
        if (
            model.provider_id == current.provider_id
            and model.model_id == current.model_id
        ):
            output_fn(f"{model.model_id}")
            output_fn(f"  provider: {model.provider_id}")
            output_fn(
                f"  tool calling: {'yes' if model.supports_tool_call else 'no'}"
            )
            output_fn(
                f"  streaming: {'yes' if model.supports_streaming else 'no'}"
            )
            if model.context_window is not None:
                output_fn(f"  context_window: {model.context_window}")
            break


def _cmd_model(
    agents: AgentService,
    current: Session,
    user_text: str,
    output_fn: Callable[[str], None],
    *,
    input_fn: Callable[[str], str | None] | None = None,
) -> Session:
    parts = user_text.split()
    if len(parts) == 1:
        # 无参数：方向键选择模型
        try:
            models = agents.list_models()
        except CodeWispError as exc:
            output_fn(f"✗ {exc}")
            return current
        if not models:
            output_fn("（无可用模型）")
            return current

        choices: list[tuple[tuple[str, str], str]] = []
        default_index = 0
        for i, model in enumerate(models):
            label = f"{model.provider_id} / {model.model_id}  —  {model.display_name}"
            choices.append(((model.provider_id, model.model_id), label))
            if (
                model.provider_id == current.provider_id
                and model.model_id == current.model_id
            ):
                default_index = i
                label = f"{label}  (current)"
                choices[-1] = ((model.provider_id, model.model_id), label)

        picked = select_option(
            "选择模型",
            choices,
            default_index=default_index,
            input_fn=input_fn,
            output_fn=output_fn,
        )
        if picked is None:
            output_fn("已取消。")
            return current
        provider_id, model_id = picked
        try:
            updated = agents.switch_session_model(
                current.session_id,
                provider_id=provider_id,
                model_id=model_id,
            )
        except (ProviderError, ModelError, CodeWispError) as exc:
            output_fn(f"✗ Model Error\n{exc}")
            return current
        output_fn(
            f"已切换模型: {updated.provider_id}/{updated.model_id}\n"
            f"Session: {updated.session_id}"
        )
        return updated

    try:
        provider_id, model_id = agents.parse_model_ref(
            *parts[1:],
            current_provider_id=current.provider_id,
        )
        updated = agents.switch_session_model(
            current.session_id,
            provider_id=provider_id,
            model_id=model_id,
        )
    except (ProviderError, ModelError, CodeWispError) as exc:
        output_fn(f"✗ Model Error\n{exc}")
        try:
            names = [m.model_id for m in agents.list_models()]
            if names:
                output_fn("\nAvailable models:")
                for name in names:
                    output_fn(f"  {name}")
        except CodeWispError:
            pass
        output_fn("\nUse /models to see available models，或 /model 进入选择菜单。")
        return current

    output_fn(
        f"已切换模型: {updated.provider_id}/{updated.model_id}\n"
        f"Session: {updated.session_id}"
    )
    return updated


def _pick_session(
    agents: AgentService,
    current: Session,
    *,
    title: str,
    output_fn: Callable[[str], None],
    input_fn: Callable[[str], str | None] | None = None,
    exclude_current: bool = False,
) -> str | None:
    items = agents.sessions.list_sessions()
    if exclude_current:
        items = [s for s in items if s.session_id != current.session_id]
    if not items:
        output_fn("（无 Session）")
        return None
    choices: list[tuple[str, str]] = []
    default_index = 0
    for i, session in enumerate(items):
        mark = " (current)" if session.session_id == current.session_id else ""
        label = (
            f"{session.session_id}  {session.title}  "
            f"[{session.provider_id}/{session.model_id}]{mark}"
        )
        choices.append((session.session_id, label))
        if session.session_id == current.session_id:
            default_index = i
    return select_option(
        title,
        choices,
        default_index=default_index,
        input_fn=input_fn,
        output_fn=output_fn,
    )


def _cmd_context(
    agents: AgentService,
    current: Session,
    user_text: str,
    output_fn: Callable[[str], None],
) -> None:
    """``/context`` [status|compact|memory] — 分层上下文诊断。"""
    parts = user_text.strip().split()
    sub = parts[1].lower() if len(parts) > 1 else "status"
    try:
        if sub in {"status", "show", "budget"}:
            status = agents.get_context_status(current.session_id)
            _render_context_status(status, output_fn=output_fn)
            return
        if sub == "compact":
            ckpt = agents.compact_context(current.session_id)
            output_fn(
                f"已创建 checkpoint: {ckpt.checkpoint_id} "
                f"(trigger={ckpt.trigger.value}, boundary={ckpt.retained_message_boundary})"
            )
            status = agents.get_context_status(current.session_id)
            _render_context_status(status, output_fn=output_fn)
            return
        if sub == "memory":
            memories = agents.list_memories(current.session_id, include_invalidated=True)
            if not memories:
                output_fn("（暂无 durable memory）")
                return
            output_fn("Durable Memory\n")
            for m in memories:
                flag = " [invalidated]" if m.invalidated else ""
                loc = f" @ {m.file_path}" if m.file_path else ""
                output_fn(
                    f"  [{m.category.value}] {m.content[:120]} "
                    f"(source={m.source_type.value}"
                    f"{':' + m.source_id if m.source_id else ''}{loc}){flag}"
                )
            return
        output_fn("用法: /context [status|compact|memory]")
    except (SessionError, CodeWispError) as exc:
        output_fn(f"错误: {exc}")


def _render_context_status(status, *, output_fn: Callable[[str], None]) -> None:
    budget = status.budget
    usable = budget.get("usable_budget", 0)
    limit = budget.get("context_limit", 0)
    output_fn("Hierarchical Context\n")
    width = max((len(s.name) for s in status.sections), default=12)
    for sec in status.sections:
        if sec.tokens <= 0 and sec.name not in {"System", "Task State", "Plan"}:
            continue
        label = f"{sec.name:<{width}}"
        tok = _format_tokens(sec.tokens)
        output_fn(f"  {label}  {tok}")
    output_fn("  " + "-" * (width + 14))
    output_fn(
        f"  {'Total':<{width}}  {_format_tokens(status.total_tokens)} / {_format_tokens(usable)}"
        f"  (window {_format_tokens(limit)}, estimator={budget.get('estimator')})"
    )
    comp = status.compaction or {}
    if comp:
        output_fn("\nCompaction:")
        output_fn(f"  automatic/manual count: {comp.get('count', 0)}")
        if comp.get("last_checkpoint_id"):
            output_fn(f"  last checkpoint: {comp.get('last_checkpoint_id')}")
            output_fn(f"  last at: {comp.get('last_checkpoint_at')}")
        if comp.get("retained_tail") is not None:
            output_fn(f"  retained tail messages: {comp.get('retained_tail')}")
        if comp.get("compacted"):
            output_fn("  last build: compacted=yes")


def _format_tokens(n: int) -> str:
    if n >= 1000:
        return f"{n / 1000:.1f}k"
    return str(n)


def _cmd_plan(
    agents: AgentService,
    current: Session,
    user_text: str,
    output_fn: Callable[[str], None],
) -> None:
    parts = user_text.strip().split(maxsplit=1)
    sub = parts[1].strip().lower() if len(parts) > 1 else "show"
    try:
        if sub in {"show", "status", ""}:
            plan = agents.get_latest_plan(current.session_id)
            if plan is None:
                output_fn("No active plan.")
                return
            from backend.app.cli.render_plan import render_plan_strip

            render_plan_strip(plan, output_fn=output_fn)
            return
        if sub == "refresh":
            plan = agents.refresh_plan(current.session_id)
            output_fn("Plan refreshed.\n")
            from backend.app.cli.render_plan import render_plan_strip

            render_plan_strip(plan, output_fn=output_fn)
            return
        output_fn("用法: /plan [show|refresh]")
    except (SessionError, CodeWispError) as exc:
        output_fn(f"错误: {exc}")


def _cmd_memory(
    agents: AgentService,
    current: Session,
    user_text: str,
    output_fn: Callable[[str], None],
) -> None:
    parts = user_text.strip().split(maxsplit=2)
    sub = parts[1].lower() if len(parts) > 1 else "help"
    try:
        if sub in {"help", ""}:
            output_fn(
                "Memory commands:\n"
                "  /memory search <query>\n"
                "  /memory index\n"
                "  /memory rebuild\n"
                "  /memory stats\n"
            )
            return
        if sub == "search":
            query = parts[2].strip() if len(parts) > 2 else ""
            if not query:
                output_fn("用法: /memory search <query>")
                return
            hits = agents.memory_search(current.session_id, query)
            if not hits:
                output_fn("（无检索结果）")
                return
            output_fn(f"Retrieved ({len(hits)}):\n")
            for h in hits:
                loc = h.path or h.source
                output_fn(f"  · [{h.source}] {loc}  score={h.score:.3f}")
                preview = " ".join(h.content.split())[:160]
                output_fn(f"    {preview}")
            return
        if sub == "index":
            stats = agents.memory_index(current.session_id)
            output_fn(
                f"Indexed: docs={stats.documents} chunks={stats.chunks} "
                f"model={stats.embedding_model}"
            )
            return
        if sub == "rebuild":
            stats = agents.memory_rebuild(current.session_id)
            output_fn(
                f"Rebuilt: docs={stats.documents} chunks={stats.chunks} "
                f"model={stats.embedding_model}"
            )
            return
        if sub == "stats":
            stats = agents.memory_stats(current.session_id)
            output_fn("Memory Index Stats")
            for k, v in stats.to_dict().items():
                output_fn(f"  {k}: {v}")
            return
        output_fn("用法: /memory [search|index|rebuild|stats]")
    except (SessionError, CodeWispError) as exc:
        output_fn(f"错误: {exc}")


def _cmd_status(
    agents: AgentService,
    current: Session,
    output_fn: Callable[[str], None],
) -> None:
    tool_count = 0
    try:
        registry = create_default_registry(workspace=Workspace(current.workspace))
        tool_count = len(registry.list_schemas())
    except Exception:  # noqa: BLE001 — status 兜底
        tool_count = 0

    runs = agents.sessions.list_runs(current.session_id)
    last_run = runs[-1] if runs else None
    run_status = last_run.status if last_run else "ready"
    perm_status = "interactive (CLI)"
    if run_status == AgentStatus.WAITING_PERMISSION.value:
        perm_status = "waiting for user decision"

    theme = get_theme()
    rows = [
        ("Session ID", current.session_id),
        ("Title", current.title),
        ("Workspace", current.workspace),
        ("Provider", current.provider_id),
        ("Model", current.model_id),
        ("Run status", run_status),
        ("Permission", perm_status),
        ("Max steps", str(agents.max_steps)),
        ("Tools", str(tool_count)),
        ("Database", str(agents.db_path)),
        (
            "Resolver",
            "configured" if agents.model_resolver is not None else "fixed llm",
        ),
        ("Theme", f"{theme.name} · color={'on' if theme.color else 'off'}"),
    ]

    if output_fn is print and theme.rich_enabled:
        from rich.table import Table

        table = Table(title="CodeWisp Status", show_header=False, box=None, padding=(0, 2))
        table.add_column("k", style="cw.key")
        table.add_column("v", style="cw.value")
        for k, v in rows:
            table.add_row(k, v)
        make_console().print(table)
        return

    output_fn("CodeWisp Status\n")
    for k, v in rows:
        output_fn(f"  {k:<12} {v}")


def _cmd_diff(
    agents: AgentService,
    current: Session,
    user_text: str,
    *,
    output_fn: Callable[[str], None],
    input_fn: Callable[[str], str | None] | None = None,
) -> None:
    """``/diff`` [step|run] [id] — 展示文件变更（Rich unified）。"""
    kind, target_id = _parse_change_target(user_text, command="/diff")
    try:
        if kind is None and target_id is None:
            run_id = _latest_run_with_changes(agents, current.session_id)
            if not run_id:
                # 尝试选择
                run_id = _pick_run_with_changes(
                    agents,
                    current,
                    title="选择要查看 Diff 的 Run",
                    output_fn=output_fn,
                    input_fn=input_fn,
                )
            if not run_id:
                output_fn("（当前 Session 尚无文件变更。完成含 edit_file/write_file 的任务后再 /diff）")
                return
            diffs = agents.get_run_file_diffs(run_id)
            run = agents.sessions.runs.get_run(run_id)
            render_file_diffs(
                diffs,
                title=f"Diff · {_human_run_label(agents, run)}",
                output_fn=output_fn,
            )
            return

        if kind == "step" or (target_id and target_id.startswith("step_")):
            step_id = target_id or _pick_step_with_changes(
                agents,
                current,
                title="选择要查看 Diff 的 Step",
                output_fn=output_fn,
                input_fn=input_fn,
            )
            if not step_id:
                output_fn("已取消。")
                return
            step = agents.sessions.runs.get_step(step_id)
            if step.session_id != current.session_id:
                output_fn("错误：该 Step 不属于当前 Session。")
                return
            run = agents.sessions.runs.get_run(step.agent_run_id)
            diffs = agents.get_step_file_diffs(step_id)
            render_file_diffs(
                diffs,
                title=f"Diff · {_human_step_label(agents, step_id, run)}",
                output_fn=output_fn,
            )
            return

        if kind == "run" or (target_id and target_id.startswith("run_")):
            run_id = target_id or _pick_run_with_changes(
                agents,
                current,
                title="选择要查看 Diff 的 Run",
                output_fn=output_fn,
                input_fn=input_fn,
            )
            if not run_id:
                output_fn("已取消。")
                return
            run = agents.sessions.runs.get_run(run_id)
            if run.session_id != current.session_id:
                output_fn("错误：该 Run 不属于当前 Session。")
                return
            diffs = agents.get_run_file_diffs(run_id)
            render_file_diffs(
                diffs,
                title=f"Diff · {_human_run_label(agents, run)}",
                output_fn=output_fn,
            )
            return

        output_fn("用法: /diff | /diff step <id> | /diff run <id>")
    except (SessionError, RevertError, CodeWispError) as exc:
        output_fn(f"错误：{exc}")
    except Exception as exc:  # noqa: BLE001
        from backend.app.persistence.errors import NotFoundError

        if isinstance(exc, NotFoundError):
            output_fn(f"错误：{exc}")
            return
        raise


def _cmd_revert(
    agents: AgentService,
    current: Session,
    user_text: str,
    *,
    output_fn: Callable[[str], None],
    input_fn: Callable[[str], str | None] | None = None,
    permission_handler=None,
    event_sink=None,
) -> None:
    """``/revert`` step|run [id] — 经 PermissionHandler 回滚工作区。"""
    kind, target_id = _parse_change_target(user_text, command="/revert")
    try:
        if kind is None and target_id is None:
            kind = select_option(
                "Revert 范围",
                [
                    ("step", "Step — 撤销单个 AgentStep"),
                    ("run", "Run — 撤销整个 AgentRun"),
                ],
                default_index=0,
                input_fn=input_fn,
                output_fn=output_fn,
            )
            if kind is None:
                output_fn("已取消。")
                return

        if kind == "step":
            step_id = target_id
            if not step_id:
                step_id = _pick_step_with_changes(
                    agents,
                    current,
                    title="选择要 Revert 的 Step",
                    output_fn=output_fn,
                    input_fn=input_fn,
                )
            if not step_id:
                output_fn("已取消。")
                return
            step = agents.sessions.runs.get_step(step_id)
            if step.session_id != current.session_id:
                output_fn("错误：该 Step 不属于当前 Session。")
                return
            diffs = agents.get_step_file_diffs(step_id)
            if diffs:
                run = agents.sessions.runs.get_run(step.agent_run_id)
                render_file_diffs(
                    diffs,
                    title=f"Will revert · {_human_step_label(agents, step_id, run)}",
                    output_fn=output_fn,
                )
            report = agents.revert_step(
                step_id,
                permission_handler=permission_handler,
                event_sink=event_sink,
            )
            _print_revert_report(report, output_fn)
            return

        if kind == "run":
            run_id = target_id
            if not run_id:
                run_id = _pick_run_with_changes(
                    agents,
                    current,
                    title="选择要 Revert 的 Run",
                    output_fn=output_fn,
                    input_fn=input_fn,
                )
            if not run_id:
                output_fn("已取消。")
                return
            run = agents.sessions.runs.get_run(run_id)
            if run.session_id != current.session_id:
                output_fn("错误：该 Run 不属于当前 Session。")
                return
            diffs = agents.get_run_file_diffs(run_id)
            if diffs:
                render_file_diffs(
                    diffs,
                    title=f"Will revert · {_human_run_label(agents, run)}",
                    output_fn=output_fn,
                )
            report = agents.revert_run(
                run_id,
                permission_handler=permission_handler,
                event_sink=event_sink,
            )
            _print_revert_report(report, output_fn)
            return

        output_fn("用法: /revert step <id> | /revert run <id> | /revert")
    except RevertError as exc:
        output_fn(f"Revert 失败：{exc}")
    except Exception as exc:  # noqa: BLE001
        from backend.app.persistence.errors import NotFoundError

        if isinstance(exc, NotFoundError):
            output_fn(f"错误：{exc}")
            return
        raise


def _print_revert_report(report, output_fn: Callable[[str], None]) -> None:
    if report.denied:
        output_fn("已拒绝 Revert（Permission DENY）。工作区未改动。")
        return
    if report.ok:
        output_fn(
            f"Revert 完成：{report.target_type} {report.target_id}\n"
            f"  已恢复文件: {', '.join(report.applied) or '（无）'}\n"
            f"  safety snapshot: {report.safety_snapshot_id}"
        )
    else:
        output_fn(
            f"Revert 部分失败：{report.target_type} {report.target_id}\n"
            f"  applied: {', '.join(report.applied) or '—'}\n"
            f"  failed: {report.failed}"
        )


def _parse_change_target(
    user_text: str, *, command: str
) -> tuple[str | None, str | None]:
    """解析 ``/diff|/revert [step|run] [id]``。"""
    parts = user_text.split()
    if len(parts) <= 1:
        return None, None
    tokens = parts[1:]
    if tokens[0] in {"step", "run"}:
        kind = tokens[0]
        tid = tokens[1] if len(tokens) > 1 else None
        return kind, tid
    raw = tokens[0]
    if raw.startswith("step_"):
        return "step", raw
    if raw.startswith("run_"):
        return "run", raw
    return None, raw


def _short_id(full_id: str) -> str:
    if "_" in full_id:
        return full_id.split("_", 1)[1][-6:]
    return full_id[-6:]


def _fmt_clock(iso: str | None) -> str:
    if not iso:
        return "—"
    # 2026-08-30T17:00:00+00:00 → 17:00
    try:
        if "T" in iso:
            return iso.split("T", 1)[1][:5]
    except Exception:  # noqa: BLE001
        pass
    return iso[:16]


def _path_names(paths: list[str], *, limit: int = 2) -> str:
    names = [Path(p).name for p in paths]
    if not names:
        return "(no files)"
    shown = ", ".join(names[:limit])
    if len(names) > limit:
        shown += f" +{len(names) - limit}"
    return shown


def _run_index(agents: AgentService, run) -> int:
    runs = agents.sessions.list_runs(run.session_id)
    for i, item in enumerate(runs, start=1):
        if item.agent_run_id == run.agent_run_id:
            return i
    return 0


def _human_run_label(agents: AgentService, run) -> str:
    changes = agents.list_run_file_changes(run.agent_run_id)
    paths = sorted({c.path for c in changes})
    idx = _run_index(agents, run)
    answer = (run.final_answer or "").strip().replace("\n", " ")
    if len(answer) > 36:
        answer = answer[:35] + "…"
    hint = f"  ·  “{answer}”" if answer else ""
    return (
        f"Run #{idx}  ·  {len(changes)} file(s): {_path_names(paths)}  ·  "
        f"{run.status}  ·  {_fmt_clock(run.created_at)}  ·  …{_short_id(run.agent_run_id)}"
        f"{hint}"
    )


def _human_step_label(agents: AgentService, step_id: str, run) -> str:
    step = agents.sessions.runs.get_step(step_id)
    changes = agents.list_step_file_changes(step_id)
    paths = sorted({c.path for c in changes})
    badges = "".join(sorted({c.change_type.value[0] for c in changes})) or "?"
    run_idx = _run_index(agents, run)
    tools = agents.sessions.runs.list_tool_calls(step_id=step_id)
    tool_names = ", ".join(dict.fromkeys(t.tool_name for t in tools if t.tool_name)) or "write"
    return (
        f"Step #{step.step_index}  ·  {tool_names}  ·  "
        f"{_path_names(paths)} [{badges}]  ·  Run #{run_idx}  ·  "
        f"{_fmt_clock(step.created_at or run.created_at)}  ·  …{_short_id(step_id)}"
    )


def _latest_run_with_changes(agents: AgentService, session_id: str) -> str | None:
    runs = agents.sessions.list_runs(session_id)
    for run in reversed(runs):
        if agents.list_run_file_changes(run.agent_run_id):
            return run.agent_run_id
    return None


def _pick_run_with_changes(
    agents: AgentService,
    current: Session,
    *,
    title: str,
    output_fn: Callable[[str], None],
    input_fn: Callable[[str], str | None] | None,
) -> str | None:
    runs = agents.sessions.list_runs(current.session_id)
    choices: list[tuple[str, str]] = []
    for run in reversed(runs):
        changes = agents.list_run_file_changes(run.agent_run_id)
        if not changes:
            continue
        choices.append((run.agent_run_id, _human_run_label(agents, run)))
    if not choices:
        return None
    return select_option(
        title, choices, default_index=0, input_fn=input_fn, output_fn=output_fn
    )


def _pick_step_with_changes(
    agents: AgentService,
    current: Session,
    *,
    title: str,
    output_fn: Callable[[str], None],
    input_fn: Callable[[str], str | None] | None,
) -> str | None:
    runs = agents.sessions.list_runs(current.session_id)
    choices: list[tuple[str, str]] = []
    seen: set[str] = set()
    for run in reversed(runs):
        for change in agents.list_run_file_changes(run.agent_run_id):
            if change.agent_step_id in seen:
                continue
            seen.add(change.agent_step_id)
            choices.append(
                (
                    change.agent_step_id,
                    _human_step_label(agents, change.agent_step_id, run),
                )
            )
    if not choices:
        return None
    return select_option(
        title, choices, default_index=0, input_fn=input_fn, output_fn=output_fn
    )
