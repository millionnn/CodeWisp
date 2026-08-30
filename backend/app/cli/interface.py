"""CodeWisp 命令行界面（V0.7 Phase 3）。

```text
CLI → AgentService / SessionService → ModelResolver → AgentLoop
```

CLI 只做输入、命令解析、状态与 AgentEvent 展示；不实现 Agent Core、不直连 SQLite。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from backend.app.agent.state import AgentStatus
from backend.app.banner import print_app_banner
from backend.app.cli.help_text import HELP_TEXT
from backend.app.cli.trace import render_agent_trace
from backend.app.llm.errors import CodeWispError
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
    output_fn("              /providers  /models  /model  /status  /delete  /exit")
    output_fn("  Type a task to continue the current Session.\n")


def read_user_input(prompt: str = "> ") -> str | None:
    """从标准输入读取一行。"""
    try:
        line = input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    return line.strip()


def _print_run_result(
    result: object,
    *,
    output_fn: Callable[[str], None],
    show_tool_trace: bool,
) -> None:
    from backend.app.services.agent_service import AgentRunResult

    assert isinstance(result, AgentRunResult)
    state = result.state

    if show_tool_trace:
        render_agent_trace(state, result.run, output_fn=output_fn)

    if state.status == AgentStatus.COMPLETED:
        output_fn(f"\nCodeWisp:\n{state.final_answer}\n")
    elif state.status == AgentStatus.MAX_STEPS:
        output_fn("\nCodeWisp:\n（已达最大步数 / 迭代预算耗尽）")
        if state.error:
            output_fn(state.error)
        if state.final_answer:
            output_fn(state.final_answer)
        output_fn("")
    elif state.status == AgentStatus.PERMISSION_REQUIRED:
        output_fn("\nCodeWisp:\n（需要用户授权，已停止自动继续）")
        if state.error:
            output_fn(state.error)
        if state.final_answer:
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
    show_tool_trace: bool = True,
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

    while True:
        user_text = input_fn("> ")
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
            output_fn(HELP_TEXT)
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

        if lower == "/model" or lower.startswith("/model "):
            current = _cmd_model(agents, current, user_text, output_fn)
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
            output_fn(
                f"已创建 Session: {current.session_id} ({current.title})\n"
                f"Model: {current.provider_id}/{current.model_id}"
            )
            continue

        if lower.startswith("/use"):
            parts = user_text.split(maxsplit=1)
            if len(parts) < 2 or not parts[1].strip():
                output_fn("用法: /use <session_id>")
                continue
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
                output_fn("用法: /delete <session_id>（别名 /rm）")
                continue
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
                output_fn(
                    f"已切换到新 Session: {current.session_id} ({current.title})"
                )
            continue

        if user_text.startswith("/"):
            output_fn("未知命令。输入 /help 查看可用命令。")
            continue

        try:
            result = agents.run(current.session_id, user_text)
            current = result.session
        except CodeWispError as exc:
            output_fn(f"错误：{exc}")
            continue

        _print_run_result(result, output_fn=output_fn, show_tool_trace=show_tool_trace)

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

    for msg in visible:
        label = "你" if msg.role == "user" else "CodeWisp"
        output_fn(f"\n[{label}]")
        output_fn(msg.content or "")


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
) -> Session:
    parts = user_text.split()
    if len(parts) == 1:
        output_fn("Current Model\n")
        output_fn(f"Provider : {current.provider_id}")
        output_fn(f"Model    : {current.model_id}")
        output_fn(f"Session  : {current.session_id}")
        output_fn(f"Workspace: {current.workspace}")
        return current

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
        output_fn("\nUse /models to see available models.")
        return current

    output_fn(
        f"已切换模型: {updated.provider_id}/{updated.model_id}\n"
        f"Session: {updated.session_id}"
    )
    return updated


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

    output_fn("CodeWisp Status\n")
    output_fn("Session")
    output_fn(f"  ID        {current.session_id}")
    output_fn(f"  Title     {current.title}")
    output_fn(f"  Workspace {current.workspace}")
    output_fn("")
    output_fn("Model")
    output_fn(f"  Provider  {current.provider_id}")
    output_fn(f"  Model     {current.model_id}")
    output_fn("")
    output_fn("Agent")
    output_fn("  Status    ready")
    output_fn(f"  Max Steps {agents.max_steps}")
    output_fn("")
    output_fn("Runtime")
    output_fn(f"  Tools     {tool_count}")
    output_fn(f"  Database  {agents.db_path}")
    if agents.model_resolver is not None:
        output_fn("  Resolver  configured")
    else:
        output_fn("  Resolver  (fixed llm / no ModelResolver)")
