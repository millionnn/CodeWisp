"""Context 优先级：P0 永不因普通 compaction 删除。"""

from __future__ import annotations

from enum import IntEnum

#定义优先级，什么绝对不能丢，什么可以先砍

class ContextPriority(IntEnum):
    """数字越小越重要。"""

    P0 = 0  # immutable：system / permission。
    P1 = 1  # critical：task / plan / decisions / project architecture
    P2 = 2  # important：modified files / recent tests
    P3 = 3  # recent：messages / tool output
    P4 = 4  # disposable：old listings / verbose output


# 语义别名，便于装配时标注
PRIORITY_LABELS: dict[ContextPriority, str] = {
    ContextPriority.P0: "immutable",
    ContextPriority.P1: "critical",
    ContextPriority.P2: "important",
    ContextPriority.P3: "recent",
    ContextPriority.P4: "disposable",
}
