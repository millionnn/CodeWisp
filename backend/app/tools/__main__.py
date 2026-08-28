"""工具系统人工验证入口（不经过 LLM / Agent Loop）。

用法：
  python -m backend.app.tools list
  python -m backend.app.tools run calculator '{"expression":"12 * 8 + 5"}'
  python -m backend.app.tools run get_current_time
"""

from __future__ import annotations

import json
import sys

from backend.app.tools.factory import create_default_executor


def _usage() -> None:
    print(
        "用法：\n"
        "  python -m backend.app.tools list\n"
        "  python -m backend.app.tools run <tool_name> [json_arguments]\n"
    )


def main(argv: list[str] | None = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if not args:
        _usage()
        return 1

    executor = create_default_executor()
    command = args[0]

    if command == "list":
        tools = executor.registry.list_tools()
        for tool in tools:
            print(f"- {tool.name}: {tool.description}")
        return 0

    if command == "run":
        if len(args) < 2:
            print("错误：缺少 tool_name。")
            _usage()
            return 1
        tool_name = args[1]
        raw_args = args[2] if len(args) >= 3 else "{}"
        try:
            parsed = json.loads(raw_args)
        except json.JSONDecodeError as exc:
            print(f"错误：参数 JSON 无法解析：{exc}")
            return 1
        if not isinstance(parsed, dict):
            print("错误：参数 JSON 必须是对象。")
            return 1

        result = executor.execute(tool_name, parsed)
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0 if result.success else 2

    print(f"未知命令：{command}")
    _usage()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
