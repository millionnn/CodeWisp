"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _reset_mcp_managers() -> None:
    """Prevent process-wide MCP manager leakage across tests."""
    from backend.app.mcp.manager import reset_managers_for_tests

    reset_managers_for_tests()
    yield
    reset_managers_for_tests()
