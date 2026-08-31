"""Tool Output 裁剪策略：语言无关，不按具体命令名硬编码。"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

#工具输出太长时，砍头留尾，与语言无关，缩减到8000token以内

@dataclass(frozen=True)
class ToolOutputPolicy:
    max_chars: int = 8_000
    max_lines: int = 200
    head_lines: int = 80
    tail_lines: int = 80

    def truncate(self, text: str, *, label: str = "tool_output") -> str:
        if not text:
            return text
        lines = text.splitlines()
        truncated_lines = False
        if len(lines) > self.max_lines:
            truncated_lines = True
            keep_head = max(0, self.head_lines)
            keep_tail = max(0, self.tail_lines)
            if keep_head + keep_tail >= self.max_lines:
                keep_head = self.max_lines // 2
                keep_tail = self.max_lines - keep_head
            omitted = len(lines) - keep_head - keep_tail
            mid = f"\n… truncated {omitted} lines ({label}) …\n"
            text = "\n".join(lines[:keep_head]) + mid + "\n".join(lines[-keep_tail:])

        if len(text) > self.max_chars:
            head = self.max_chars // 2
            tail = self.max_chars - head - 80
            text = (
                text[:head]
                + f"\n… truncated chars ({label}, was {len(text)} chars"
                + (", lines already truncated" if truncated_lines else "")
                + ") …\n"
                + text[-max(tail, 0) :]
            )
        return text


DEFAULT_TOOL_OUTPUT_POLICY = ToolOutputPolicy()


def prune_tool_observation(
    observation: str,
    *,
    tool_name: str | None = None,
    policy: ToolOutputPolicy | None = None,
) -> str:
    """对任意工具 observation 做统一裁剪（search / command / 其它）。"""
    pol = policy or DEFAULT_TOOL_OUTPUT_POLICY
    label = (tool_name or "tool").strip() or "tool"
    return pol.truncate(observation, label=label)


def looks_like_test_failure(text: str) -> bool:
    """启发式：输出是否像测试失败（不绑定具体 runner）。"""
    lower = text.lower()
    markers = (
        "failed",
        "failure",
        "error",
        "traceback",
        "assert",
        "failures=",
        " !== ",
        "expected:",
        "FAILED",
    )
    if "passed" in lower and "failed" not in lower and "failure" not in lower:
        # 粗略：通过
        return False
    return any(m.lower() in lower for m in markers)


def summarize_test_observation(text: str, *, max_len: int = 240) -> str:
    compact = " ".join(text.split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3] + "..."


def extract_paths_from_tool_payload(payload: dict[str, Any] | None) -> list[str]:
    """从工具结果/参数中提取可能的文件路径。"""
    if not payload:
        return []
    paths: list[str] = []
    for key in ("path", "file", "file_path", "filepath"):
        val = payload.get(key)
        if isinstance(val, str) and val.strip():
            paths.append(val.replace("\\", "/").lstrip("./"))
    output = payload.get("output")
    if isinstance(output, dict):
        paths.extend(extract_paths_from_tool_payload(output))
    return paths
