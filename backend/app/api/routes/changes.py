"""V0.9 Workspace Change Management REST（Diff / Snapshot / Revert）。

供未来 Web UI；CLI 仍直接调 AgentService，不经本路由。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from backend.app.api.deps import get_agent_service, get_session_service
from backend.app.api.schemas import (
    DiffResponse,
    FileChangeResponse,
    FileDiffResponse,
    RevertRequest,
    RevertResponse,
    SnapshotFileResponse,
    SnapshotResponse,
    StepSnapshotsResponse,
)
from backend.app.changes.diff import format_unified_diff
from backend.app.changes.errors import RevertError, SnapshotNotFoundError
from backend.app.changes.models import FileDiff, RevertReport, WorkspaceSnapshot
from backend.app.permissions.handler import AlwaysAllowPermissionHandler
from backend.app.persistence.errors import NotFoundError
from backend.app.services.agent_service import AgentService
from backend.app.session.errors import InvalidSessionError
from backend.app.session.service import SessionService

router = APIRouter(tags=["changes"])


def _file_change_to_response(c) -> FileChangeResponse:
    return FileChangeResponse(
        change_id=c.change_id,
        session_id=c.session_id,
        agent_run_id=c.agent_run_id,
        agent_step_id=c.agent_step_id,
        path=c.path,
        change_type=c.change_type.value
        if hasattr(c.change_type, "value")
        else str(c.change_type),
        tool_call_id=c.tool_call_id,
        before_snapshot_id=c.before_snapshot_id,
        after_snapshot_id=c.after_snapshot_id,
        created_at=c.created_at,
    )


def _diff_to_response(d: FileDiff) -> FileDiffResponse:
    return FileDiffResponse(
        path=d.path,
        change_type=d.change_type.value,
        before=d.before,
        after=d.after,
    )


def _snapshot_to_response(snap: WorkspaceSnapshot | None) -> SnapshotResponse | None:
    if snap is None:
        return None
    return SnapshotResponse(
        snapshot_id=snap.snapshot_id,
        workspace_root=snap.workspace_root,
        reason=snap.reason,
        files=[
            SnapshotFileResponse(
                path=f.path,
                exists=f.exists,
                content=f.content,
                size=f.size,
                content_hash=f.content_hash,
            )
            for f in snap.files
        ],
        session_id=snap.session_id,
        agent_run_id=snap.agent_run_id,
        agent_step_id=snap.agent_step_id,
        tool_call_id=snap.tool_call_id,
        created_at=snap.created_at,
    )


def _revert_to_response(report: RevertReport) -> RevertResponse:
    return RevertResponse(
        target_type=report.target_type,
        target_id=report.target_id,
        ok=report.ok,
        denied=report.denied,
        safety_snapshot_id=report.safety_snapshot_id,
        restored_snapshot_ids=list(report.restored_snapshot_ids),
        applied=list(report.applied),
        failed=[{"path": p, "error": e} for p, e in report.failed],
    )


def _ensure_run_in_session(
    agents: AgentService,
    sessions: SessionService,
    session_id: str,
    run_id: str,
):
    sessions.get_session(session_id)
    try:
        run = agents.sessions.runs.get_run(run_id)
    except NotFoundError as exc:
        raise NotFoundError(str(exc)) from exc
    if run.session_id != session_id:
        raise InvalidSessionError("Run 不属于该 Session")
    return run


def _ensure_step_in_session(
    agents: AgentService,
    sessions: SessionService,
    session_id: str,
    step_id: str,
):
    sessions.get_session(session_id)
    try:
        step = agents.sessions.runs.get_step(step_id)
    except NotFoundError as exc:
        raise NotFoundError(str(exc)) from exc
    if step.session_id != session_id:
        raise InvalidSessionError("Step 不属于该 Session")
    return step


@router.get(
    "/api/sessions/{session_id}/runs/{run_id}/changes",
    response_model=list[FileChangeResponse],
)
def list_run_changes(
    session_id: str,
    run_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> list[FileChangeResponse]:
    _ensure_run_in_session(agents, sessions, session_id, run_id)
    return [
        _file_change_to_response(c)
        for c in agents.list_run_file_changes(run_id)
    ]


@router.get(
    "/api/sessions/{session_id}/runs/{run_id}/diff",
    response_model=DiffResponse,
)
def get_run_diff(
    session_id: str,
    run_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> DiffResponse:
    _ensure_run_in_session(agents, sessions, session_id, run_id)
    diffs = agents.get_run_file_diffs(run_id)
    return DiffResponse(
        scope="run",
        scope_id=run_id,
        files=[_diff_to_response(d) for d in diffs],
        unified_diff=format_unified_diff(diffs),
    )


@router.post(
    "/api/sessions/{session_id}/runs/{run_id}/revert",
    response_model=RevertResponse,
)
def revert_run(
    session_id: str,
    run_id: str,
    body: RevertRequest,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> RevertResponse:
    if not body.confirm:
        raise InvalidSessionError("revert 需要 confirm=true")
    _ensure_run_in_session(agents, sessions, session_id, run_id)
    report = agents.revert_run(
        run_id,
        permission_handler=AlwaysAllowPermissionHandler(),
    )
    return _revert_to_response(report)


@router.get(
    "/api/sessions/{session_id}/steps/{step_id}/changes",
    response_model=list[FileChangeResponse],
)
def list_step_changes(
    session_id: str,
    step_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> list[FileChangeResponse]:
    _ensure_step_in_session(agents, sessions, session_id, step_id)
    return [
        _file_change_to_response(c)
        for c in agents.list_step_file_changes(step_id)
    ]


@router.get(
    "/api/sessions/{session_id}/steps/{step_id}/diff",
    response_model=DiffResponse,
)
def get_step_diff(
    session_id: str,
    step_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> DiffResponse:
    _ensure_step_in_session(agents, sessions, session_id, step_id)
    diffs = agents.get_step_file_diffs(step_id)
    return DiffResponse(
        scope="step",
        scope_id=step_id,
        files=[_diff_to_response(d) for d in diffs],
        unified_diff=format_unified_diff(diffs),
    )


@router.get(
    "/api/sessions/{session_id}/steps/{step_id}/snapshots",
    response_model=StepSnapshotsResponse,
)
def get_step_snapshots(
    session_id: str,
    step_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> StepSnapshotsResponse:
    _ensure_step_in_session(agents, sessions, session_id, step_id)
    before, after = agents.get_step_snapshots(step_id)
    return StepSnapshotsResponse(
        step_id=step_id,
        before=_snapshot_to_response(before),
        after=_snapshot_to_response(after),
    )


@router.post(
    "/api/sessions/{session_id}/steps/{step_id}/revert",
    response_model=RevertResponse,
)
def revert_step(
    session_id: str,
    step_id: str,
    body: RevertRequest,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> RevertResponse:
    if not body.confirm:
        raise InvalidSessionError("revert 需要 confirm=true")
    _ensure_step_in_session(agents, sessions, session_id, step_id)
    report = agents.revert_step(
        step_id,
        permission_handler=AlwaysAllowPermissionHandler(),
    )
    return _revert_to_response(report)


@router.get(
    "/api/snapshots/{snapshot_id}",
    response_model=SnapshotResponse,
)
def get_snapshot(
    snapshot_id: str,
    agents: AgentService = Depends(get_agent_service),
) -> SnapshotResponse:
    try:
        snap = agents.get_snapshot(snapshot_id)
    except SnapshotNotFoundError as exc:
        raise SnapshotNotFoundError(str(exc)) from exc
    resp = _snapshot_to_response(snap)
    assert resp is not None
    return resp
