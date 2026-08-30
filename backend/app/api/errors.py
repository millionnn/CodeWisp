"""API 错误码与异常处理。"""

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


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(SessionNotFoundError)
    async def _session_not_found(_request: Request, exc: SessionNotFoundError) -> JSONResponse:
        return JSONResponse(
            status_code=404,
            content={"error": "SESSION_NOT_FOUND", "detail": str(exc)},
        )

    @app.exception_handler(InvalidSessionError)
    async def _invalid_session(_request: Request, exc: InvalidSessionError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "INVALID_SESSION", "detail": str(exc)},
        )

    @app.exception_handler(InvalidWorkspaceError)
    async def _invalid_workspace(_request: Request, exc: InvalidWorkspaceError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "INVALID_WORKSPACE", "detail": str(exc)},
        )

    @app.exception_handler(InvalidMessageError)
    async def _invalid_message(_request: Request, exc: InvalidMessageError) -> JSONResponse:
        return JSONResponse(
            status_code=400,
            content={"error": "INVALID_MESSAGE", "detail": str(exc)},
        )

    @app.exception_handler(SessionBusyError)
    async def _session_busy(_request: Request, exc: SessionBusyError) -> JSONResponse:
        return JSONResponse(
            status_code=409,
            content={"error": "SESSION_BUSY", "detail": str(exc)},
        )
