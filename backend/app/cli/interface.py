"""CodeWisp 命令行界面。

职责：仅处理终端输入输出。
LLM 调用通过 LLMClient 完成，本模块不嵌入 HTTP 逻辑。
"""

from __future__ import annotations

from collections.abc import Callable

from backend.app.llm.client import LLMClient
from backend.app.llm.errors import CodeWispError
from backend.app.llm.messages import Conversation

DEFAULT_SYSTEM_PROMPT = (
    "你是 CodeWisp，一名编程助手。"
    "请清晰、简洁地回答用户问题。"
    "当前版本仅支持对话，尚不能读写文件或执行命令。"
)

EXIT_COMMANDS = frozenset({"/exit", "/quit", "exit", "quit"})


def print_banner() -> None:
    print("CodeWisp")
    print("输入问题后回车即可对话。输入 /exit 或 /quit 退出。\n")


def read_user_input(prompt: str = "> ") -> str | None:
    """从标准输入读取一行。

    返回：
        去除首尾空白后的用户文本；空行为空字符串；
        用户发出 EOF / 中断信号时返回 None（应退出）。
    """
    try:
        line = input(prompt)
    except (EOFError, KeyboardInterrupt):
        print()
        return None
    return line.strip()


def run_cli(
    client: LLMClient,
    *,
    system_prompt: str = DEFAULT_SYSTEM_PROMPT,
    input_fn: Callable[[str], str | None] = read_user_input,
    output_fn: Callable[[str], None] = print,
) -> int:
    """交互式多轮对话循环。

    input_fn / output_fn 可注入，便于测试在无真实终端时驱动 CLI。
    """
    print_banner()

    conversation = Conversation()
    conversation.add_system(system_prompt)

    while True:
        user_text = input_fn("> ")
        if user_text is None:
            output_fn("再见。")
            return 0

        # 在此统一 strip，保证注入的 input_fn 与真实 stdin 行为一致。
        user_text = user_text.strip()

        if user_text == "":
            output_fn("（已忽略空输入）")
            continue

        if user_text.lower() in EXIT_COMMANDS:
            output_fn("再见。")
            return 0

        conversation.add_user(user_text)

        try:
            reply = client.chat(conversation)
        except CodeWispError as exc:
            # 回滚本轮 user，避免失败请求污染对话历史。
            conversation.messages.pop()
            output_fn(f"错误：{exc}")
            continue

        conversation.add_assistant(reply)
        output_fn(f"CodeWisp:\n{reply}\n")

    return 0  # pragma: no cover
