"""API 错误码与异常处理。"""
#api层的异常处理
from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from backend.app.session.errors import (
    InvalidMessageError,
    InvalidSessionError,
    InvalidWorkspaceError,
    SessionBusyError,
    SessionNotFoundError,
)
from backend.app.permissions.errors import PermissionError as DomainPermissionError
from backend.app.changes.errors import (
    ChangeError,
    RevertError,
    SnapshotNotFoundError,
)
from backend.app.persistence.errors import NotFoundError as PersistenceNotFoundError


#注册一个异常处理
def register_exception_handlers(app: FastAPI) -> None:
    #session不存在异常处理
    @app.exception_handler(SessionNotFoundError)
    async def _session_not_found(_request: Request, exc: SessionNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": "SESSION_NOT_FOUND", "detail": str(exc)},
        )

    @app.exception_handler(PersistenceNotFoundError)
    async def _persistence_not_found(
        _request: Request, exc: PersistenceNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": "NOT_FOUND", "detail": str(exc)},
        )

    @app.exception_handler(SnapshotNotFoundError)
    async def _snapshot_not_found(
        _request: Request, exc: SnapshotNotFoundError
    ) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": "SNAPSHOT_NOT_FOUND", "detail": str(exc)},
        )

    @app.exception_handler(RevertError)
    async def _revert_error(_request: Request, exc: RevertError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "REVERT_ERROR", "detail": str(exc)},
        )

    @app.exception_handler(ChangeError)
    async def _change_error(_request: Request, exc: ChangeError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "CHANGE_ERROR", "detail": str(exc)},
        )

    #session无效异常处理
    @app.exception_handler(InvalidSessionError)
    async def _invalid_session(_request: Request, exc: InvalidSessionError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "INVALID_SESSION", "detail": str(exc)},
        )

    #工作空间无效异常处理
    @app.exception_handler(InvalidWorkspaceError)
    async def _invalid_workspace(_request: Request, exc: InvalidWorkspaceError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "INVALID_WORKSPACE", "detail": str(exc)},
        )

    #消息无效异常处理
    @app.exception_handler(InvalidMessageError)
    async def _invalid_message(_request: Request, exc: InvalidMessageError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "INVALID_MESSAGE", "detail": str(exc)},
        )

    #session繁忙异常处理
    @app.exception_handler(SessionBusyError)
    async def _session_busy(_request: Request, exc: SessionBusyError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": "SESSION_BUSY", "detail": str(exc)},
        )

    @app.exception_handler(DomainPermissionError)
    async def _permission_error(_request: Request, exc: DomainPermissionError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "PERMISSION_ERROR", "detail": str(exc)},
        )
