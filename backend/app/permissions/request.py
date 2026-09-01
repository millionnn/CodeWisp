"""PermissionRequest：ASK 时交给 PermissionHandler 的授权请求。"""

#ASK 时交给 PermissionHandler 的授权请求(我想执行这条命令的申请单)

from __future__ import annotations

import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def new_permission_request_id() -> str:
    return f"perm_{uuid.uuid4().hex}"

#权限请求
@dataclass(frozen=True)
class PermissionRequest:
    """一次需要用户确认的操作请求（不含凭据）。"""

    command: str
    args: tuple[str, ...] = ()
    cwd: str = "."
    reason: str = ""
    tool_name: str = "run_command"
    request_id: str = field(default_factory=new_permission_request_id)
    created_at: str = field(default_factory=_utc_now_iso)
    session_id: str | None = None
    agent_run_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["args"] = list(self.args)
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> PermissionRequest:
        if not isinstance(data, dict):
            raise TypeError("PermissionRequest.from_dict 需要 dict")
        command = data.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("command 必须是非空字符串")
        raw_args = data.get("args") or []
        if not isinstance(raw_args, list):
            raise ValueError("args 必须是 list")
        return cls(
            command=command.strip(),
            args=tuple(str(a) for a in raw_args),
            cwd=str(data.get("cwd") or "."),
            reason=str(data.get("reason") or ""),
            tool_name=str(data.get("tool_name") or "run_command"),
            request_id=str(data.get("request_id") or new_permission_request_id()),
            created_at=str(data.get("created_at") or _utc_now_iso()),
            session_id=data.get("session_id"),
            agent_run_id=data.get("agent_run_id"),
        )
