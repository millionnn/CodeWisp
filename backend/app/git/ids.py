"""Git domain identifiers (reserved for future use)."""

from __future__ import annotations

import uuid


def new_git_operation_id() -> str:
    return f"gitop_{uuid.uuid4().hex[:12]}"
