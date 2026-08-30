"""CLI 包。"""

from __future__ import annotations

__all__ = ["run_cli"]


def __getattr__(name: str):
    if name == "run_cli":
        from backend.app.cli.interface import run_cli

        return run_cli
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
