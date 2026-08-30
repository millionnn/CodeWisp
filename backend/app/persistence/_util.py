"""时间戳与 JSON 辅助（Repository 共用）。"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    # 保留微秒，避免同一秒内多条 Run 排序不稳定
    return datetime.now(timezone.utc).isoformat()


def dumps_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def loads_json(text: str | None, *, default: Any = None) -> Any:
    if text is None or text == "":
        return default
    return json.loads(text)
