"""V1.1 Git REST API — status / diff / log / branches / commit."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_agent_service, get_session_service
from backend.app.api.schemas import (
    GitBranchResponse,
    GitBranchesResponse,
    GitCommitRequest,
    GitCommitResponse,
    GitCommitResultResponse,
    GitDiffFileResponse,
    GitDiffResponse,
    GitFileStatusResponse,
    GitLogResponse,
    GitRepositoryInfoResponse,
    GitStatusResponse,
)
from backend.app.git.errors import GitNotRepositoryError
from backend.app.git.models import GitRepositoryInfo, GitStatus
from backend.app.permissions.handler import AlwaysAllowPermissionHandler
from backend.app.services.agent_service import AgentService
from backend.app.session.errors import InvalidMessageError, InvalidSessionError
from backend.app.session.service import SessionService

router = APIRouter(tags=["git"])


def _status_response(result: GitStatus | GitRepositoryInfo) -> GitStatusResponse | GitRepositoryInfoResponse:
    if isinstance(result, GitRepositoryInfo) or hasattr(result, "is_git_repository") and not getattr(result, "branch", None) and not isinstance(result, GitStatus):
        if isinstance(result, GitRepositoryInfo):
            info = result
        else:
            info = GitRepositoryInfo(
                is_git_repository=getattr(result, "is_git_repository", False),
                workspace=getattr(result, "workspace", ""),
                repository_root=getattr(result, "repository_root", None),
            )
        if not info.is_git_repository:
            return GitRepositoryInfoResponse(**info.to_dict())  # type: ignore[return-value]
    if isinstance(result, GitRepositoryInfo) and not result.is_git_repository:
        return GitRepositoryInfoResponse(**result.to_dict())  # type: ignore[return-value]

    status = result if isinstance(result, GitStatus) else None
    if status is None:
        raise GitNotRepositoryError("不是 Git 仓库")
    return GitStatusResponse(
        is_git_repository=True,
        repository_root=status.repository_root,
        branch=status.branch,
        ahead=status.ahead,
        behind=status.behind,
        clean=status.clean,
        detached=status.detached,
        modified_count=status.modified_count,
        staged_count=status.staged_count,
        untracked_count=status.untracked_count,
        files=[GitFileStatusResponse(**f.to_dict()) for f in status.all_files],
    )


@router.get(
    "/api/sessions/{session_id}/git/status",
    response_model=GitStatusResponse | GitRepositoryInfoResponse,
)
def get_git_status(
    session_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
):
    sessions.get_session(session_id)
    result = agents.git_status(session_id)
    return _status_response(result)


@router.get(
    "/api/sessions/{session_id}/git/diff",
    response_model=GitDiffResponse,
)
def get_git_diff(
    session_id: str,
    path: str | None = Query(default=None),
    staged: bool = Query(default=False),
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> GitDiffResponse:
    sessions.get_session(session_id)
    try:
        diff = agents.git_diff(session_id, path=path, staged=staged)
    except GitNotRepositoryError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return GitDiffResponse(
        staged=diff.staged,
        total_additions=diff.total_additions,
        total_deletions=diff.total_deletions,
        files=[GitDiffFileResponse(**f.to_dict()) for f in diff.files],
        patch=diff.patch,
    )


@router.get(
    "/api/sessions/{session_id}/git/log",
    response_model=GitLogResponse,
)
def get_git_log(
    session_id: str,
    limit: int = Query(default=20, ge=1, le=100),
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> GitLogResponse:
    sessions.get_session(session_id)
    try:
        commits = agents.git_log(session_id, limit=limit)
    except GitNotRepositoryError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return GitLogResponse(
        commits=[GitCommitResponse(**c.to_dict()) for c in commits],
        count=len(commits),
    )


@router.get(
    "/api/sessions/{session_id}/git/branches",
    response_model=GitBranchesResponse,
)
def get_git_branches(
    session_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> GitBranchesResponse:
    sessions.get_session(session_id)
    try:
        branches = agents.git_branches(session_id)
        current = agents._git_service_for_session(session_id).current_branch()  # noqa: SLF001
    except GitNotRepositoryError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return GitBranchesResponse(
        current=current,
        branches=[GitBranchResponse(**b.to_dict()) for b in branches],
    )


@router.post(
    "/api/sessions/{session_id}/git/commit",
    response_model=GitCommitResultResponse,
)
def post_git_commit(
    session_id: str,
    body: GitCommitRequest,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> GitCommitResultResponse:
    sessions.get_session(session_id)
    if not body.confirm:
        raise InvalidMessageError("git commit 需要 confirm=true")
    try:
        result = agents.git_commit(
            session_id,
            message=body.message,
            paths=body.paths or None,
            confirm=body.confirm,
            permission_handler=AlwaysAllowPermissionHandler(),
        )
    except GitNotRepositoryError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return GitCommitResultResponse(
        ok=result.get("ok", False),
        denied=result.get("denied", False),
        commit_id=result.get("commit_id"),
        branch=result.get("branch"),
        message=result.get("message"),
        commit_preview=result.get("commit_preview"),
    )
