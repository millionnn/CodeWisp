"""CodeWisp 命令行界面（V0.6 Phase 4）。

```text
CLI → AgentService → SessionService → AgentLoop
```

支持创建 / 切换 / 删除 / 续跑 / 查看 Session；不做复杂 TUI。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from backend.app.agent.state import AgentStatus
from backend.app.banner import print_app_banner
from backend.app.llm.errors import CodeWispError
from backend.app.services.agent_service import AgentService
from backend.app.session.errors import SessionError, SessionNotFoundError
from backend.app.session.models import Session

EXIT_COMMANDS = frozenset({"/exit", "/quit", "exit", "quit"})
DELETE_COMMANDS = frozenset({"/delete", "/rm"})


#打印一个启动条
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
    output_fn(
        "  Commands  : /sessions  /session  /new [title]  /use <id>  "
        "/delete <id>  /history  /exit"
    )
    output_fn("  Type a task to continue the current Session.\n")

#读取用户输入
def read_user_input(prompt: str = "> ") -> str | None:
    """从标准输入读取一行。"""
    try:
        line = input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    return line.strip()

#打印一个agent工作结果
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
        for event in state.events:
            if event.event_type == "tool_completed":
                out = (event.metadata or {}).get("output")
                output_fn(f"[工具] {event.tool_name} → {out}")
            elif event.event_type == "tool_failed":
                err = (event.metadata or {}).get("error")
                output_fn(f"[工具失败] {event.tool_name}：{err}")

    if state.status == AgentStatus.COMPLETED:
        output_fn(f"CodeWisp:\n{state.final_answer}\n")
    elif state.status == AgentStatus.MAX_STEPS:
        output_fn(f"CodeWisp:\n（已达最大步数 / 迭代预算耗尽）{state.error}\n")
        if state.final_answer:
            output_fn(state.final_answer)
    elif state.status == AgentStatus.PERMISSION_REQUIRED:
        output_fn(f"CodeWisp:\n（需要用户授权，已停止自动继续）{state.error}\n")
        if state.final_answer:
            output_fn(state.final_answer)
    elif state.status == AgentStatus.FAILED:
        output_fn(f"错误：{state.error}")
    else:
        output_fn(f"错误：意外状态 {state.status}")


def _session_has_dialogue(agents: AgentService, session_id: str) -> bool:
    """是否已与 LLM 产生过对话（有 AgentRun 即算使用过）。"""
    return bool(agents.sessions.list_runs(session_id))


def _discard_unused_session(
    agents: AgentService,
    session: Session,
    *,
    output_fn: Callable[[str], None] | None = None,
) -> bool:
    """若 Session 从未对话则删除，避免留下空壳。返回是否已丢弃。"""
    if _session_has_dialogue(agents, session.session_id):
        return False
    try:
        agents.sessions.delete_session(session.session_id)
    except SessionError:
        return False
    if output_fn is not None:
        output_fn(f"（已丢弃未使用的空 Session: {session.session_id}）")
    return True


#运行一个cli
def run_cli(
    agents: AgentService,
    *,
    workspace_root: Path,
    session_id: str | None = None,
    session_title: str = "CLI Session",
    provider_id: str = "deepseek",
    model_id: str = "deepseek-chat",
    input_fn: Callable[[str], str | None] = read_user_input,
    output_fn: Callable[[str], None] = print,
    show_tool_trace: bool = False,
) -> int:
    """交互式入口：Session 命令 + 用户任务经 AgentService.run。"""
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

        #获取所有session
        if lower == "/sessions":
            _cmd_sessions(agents, current, output_fn)
            continue
        #获取一个session
        if lower == "/session":
            _cmd_session(current, output_fn)
            continue
        #获取一个session的历史记录
        if lower == "/history":
            _cmd_history(agents, current.session_id, output_fn)
            continue
        #创建一个session
        if lower.startswith("/new"):
            rest = user_text[4:].strip()
            title = rest or "CLI Session"
            _discard_unused_session(agents, current, output_fn=output_fn)
            try:
                current = agents.sessions.create_session(
                    title=title,
                    workspace=workspace_root,
                    provider_id=provider_id,
                    model_id=model_id,
                )
            except SessionError as exc:
                output_fn(f"错误：{exc}")
                continue
            output_fn(f"已创建 Session: {current.session_id} ({current.title})")
            continue
        #切换一个session
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
                f"Workspace: {current.workspace}"
            )
            continue
        #删除一个session
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
            output_fn(
                "未知命令。可用: /sessions /session /new /use /delete /history /exit"
            )
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
    for session in items:
        mark = "*" if session.session_id == current.session_id else " "
        output_fn(
            f"{mark} {session.session_id}  {session.title}  "
            f"[{session.provider_id}/{session.model_id}]  {session.workspace}"
        )


def _cmd_session(current: Session, output_fn: Callable[[str], None]) -> None:
    output_fn(
        f"session_id: {current.session_id}\n"
        f"title: {current.title}\n"
        f"workspace: {current.workspace}\n"
        f"provider/model: {current.provider_id}/{current.model_id}\n"
        f"status: {current.status}"
    )


def _cmd_history(
    agents: AgentService,
    session_id: str,
    output_fn: Callable[[str], None],
) -> None:
    """展示用户与助手的可读对话（完整正文，不含 system/tool 轨迹）。"""
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
