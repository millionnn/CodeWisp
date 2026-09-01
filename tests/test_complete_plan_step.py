"""complete_plan_step：显式逐步推进 Plan。"""

from __future__ import annotations

from pathlib import Path

from backend.app.context.budget import ContextBudget
from backend.app.context.manager import DefaultContextManager
from backend.app.context.models import PlanStepStatus
from backend.app.persistence.context_repository import ContextRepository
from backend.app.persistence.store import SqliteStore
from backend.app.session.service import SessionService
from backend.app.tools.builtin.plan_step import create_complete_plan_step_tool
from backend.app.tools.factory import create_default_registry
from backend.app.workspace.workspace import Workspace


def test_complete_plan_step_tool_advances(tmp_path: Path) -> None:
    store = SqliteStore(tmp_path / "p.db")
    store.connect()
    session = SessionService(store).create_session(workspace=str(tmp_path), title="t")
    repo = ContextRepository(store)
    cm = DefaultContextManager(
        session_id=session.session_id,
        workspace_root=str(tmp_path),
        budget=ContextBudget.from_context_window(8_000),
        repository=repo,
    )
    cm.begin_run("做一件事", agent_run_id=None)
    assert cm.plan is not None
    assert cm.plan.steps[0].status == PlanStepStatus.IN_PROGRESS

    tool = create_complete_plan_step_tool(complete_fn=cm.complete_current_step)
    result = tool.execute({"note": "step1 done"})
    assert result.success
    assert result.output["completed_step_index"] == 0
    assert cm.plan.steps[0].status == PlanStepStatus.COMPLETED
    assert cm.plan.steps[1].status == PlanStepStatus.IN_PROGRESS


def test_registry_includes_complete_plan_step(tmp_path: Path) -> None:
    ws = Workspace(tmp_path)
    reg = create_default_registry(workspace=ws, plan_complete_fn=lambda **_: {"ok": True})
    names = {s["function"]["name"] for s in reg.list_schemas()}
    assert "complete_plan_step" in names
