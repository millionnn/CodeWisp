"""CodeWisp 命令行界面。

职责：终端输入输出。
Agent 编排由 AgentLoop 完成，本模块不实现工具循环。
"""

from __future__ import annotations

from collections.abc import Callable

from backend.app.agent.loop import AgentLoop, DEFAULT_AGENT_SYSTEM_PROMPT
from backend.app.agent.state import AgentStatus
from backend.app.llm.errors import CodeWispError
from backend.app.llm.messages import Conversation

EXIT_COMMANDS = frozenset({"/exit", "/quit", "exit", "quit"})


def print_banner() -> None:
    print("CodeWisp")
    print("输入任务后回车。Agent 可调用工具完成计算/查时等。输入 /exit 退出。\n")


def read_user_input(prompt: str = "> ") -> str | None:
    """从标准输入读取一行。"""
    try:
        line = input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    return line.strip()


def run_cli(
    agent: AgentLoop,
    *,
    system_prompt: str = DEFAULT_AGENT_SYSTEM_PROMPT,
    input_fn: Callable[[str], str | None] = read_user_input,
    output_fn: Callable[[str], None] = print,
    show_tool_trace: bool = True,
) -> int:
    """交互式多轮任务入口：每次用户输入交给 AgentLoop.run。"""
    print_banner()

    conversation = Conversation()
    conversation.add_system(system_prompt)

    while True:
        user_text = input_fn("> ")
        if user_text is None:
            output_fn("再见。")
            return 0

        user_text = user_text.strip()

        if user_text == "":
            output_fn("（已忽略空输入）")
            continue

        if user_text.lower() in EXIT_COMMANDS:
            output_fn("再见。")
            return 0

        try:
            state = agent.run(user_text, conversation=conversation)
        except CodeWispError as exc:
            output_fn(f"错误：{exc}")
            continue

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
            output_fn(f"CodeWisp:\n（已达最大步数）{state.error}\n")
            if state.final_answer:
                output_fn(state.final_answer)
        elif state.status == AgentStatus.FAILED:
            output_fn(f"错误：{state.error}")
        else:
            output_fn(f"错误：意外状态 {state.status}")

    return 0  # pragma: no cover
