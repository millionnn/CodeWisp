"""V1.2 LSP / Code Intelligence REST API."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import get_agent_service, get_session_service
from backend.app.api.schemas import (
    LspDefinitionResponse,
    LspDiagnosticResponse,
    LspDiagnosticsResponse,
    LspHoverResponse,
    LspLocationResponse,
    LspPositionResponse,
    LspRangeResponse,
    LspReferencesResponse,
    LspStatusResponse,
    LspSymbolResponse,
    LspSymbolsResponse,
)
from backend.app.lsp.errors import LspError
from backend.app.lsp.models import Diagnostic, Location, Range, Symbol
from backend.app.services.agent_service import AgentService
from backend.app.session.errors import InvalidSessionError
from backend.app.session.service import SessionService

router = APIRouter(tags=["lsp"])


def _range_resp(rng: Range | None) -> LspRangeResponse | None:
    if rng is None:
        return None
    return LspRangeResponse(
        start=LspPositionResponse(line=rng.start.line, character=rng.start.character),
        end=LspPositionResponse(line=rng.end.line, character=rng.end.character),
    )


def _diag_resp(d: Diagnostic) -> LspDiagnosticResponse:
    return LspDiagnosticResponse(
        message=d.message,
        severity=d.severity.value,
        source=d.source,
        code=d.code,
        path=d.path,
        range=_range_resp(d.range),
    )


def _loc_resp(loc: Location) -> LspLocationResponse:
    return LspLocationResponse(
        path=loc.path,
        uri=loc.uri,
        range=_range_resp(loc.range),
    )


def _sym_resp(s: Symbol) -> LspSymbolResponse:
    return LspSymbolResponse(
        name=s.name,
        kind=s.kind.value,
        path=s.path,
        range=_range_resp(s.range),
        children=[_sym_resp(c) for c in s.children],
    )


@router.get(
    "/api/sessions/{session_id}/lsp/status",
    response_model=LspStatusResponse,
)
def get_lsp_status(
    session_id: str,
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> LspStatusResponse:
    sessions.get_session(session_id)
    status = agents.lsp_status(session_id)
    return LspStatusResponse(**status.to_dict())


@router.get(
    "/api/sessions/{session_id}/lsp/diagnostics",
    response_model=LspDiagnosticsResponse,
)
def get_lsp_diagnostics(
    session_id: str,
    path: str | None = Query(default=None),
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> LspDiagnosticsResponse:
    sessions.get_session(session_id)
    try:
        diags = agents.lsp_diagnostics(session_id, path=path)
    except LspError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return LspDiagnosticsResponse(
        path=path,
        count=len(diags),
        diagnostics=[_diag_resp(d) for d in diags],
    )


@router.get(
    "/api/sessions/{session_id}/lsp/symbols",
    response_model=LspSymbolsResponse,
)
def get_lsp_symbols(
    session_id: str,
    path: str = Query(...),
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> LspSymbolsResponse:
    sessions.get_session(session_id)
    try:
        symbols = agents.lsp_symbols(session_id, path=path)
    except LspError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return LspSymbolsResponse(
        path=path,
        count=len(symbols),
        symbols=[_sym_resp(s) for s in symbols],
    )


@router.get(
    "/api/sessions/{session_id}/lsp/definition",
    response_model=LspDefinitionResponse,
)
def get_lsp_definition(
    session_id: str,
    path: str = Query(...),
    line: int = Query(..., ge=0),
    character: int = Query(..., ge=0),
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> LspDefinitionResponse:
    sessions.get_session(session_id)
    try:
        result = agents.lsp_definition(
            session_id, path=path, line=line, character=character
        )
    except LspError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return LspDefinitionResponse(
        path=path,
        line=line,
        character=character,
        locations=[_loc_resp(loc) for loc in result.locations],
    )


@router.get(
    "/api/sessions/{session_id}/lsp/references",
    response_model=LspReferencesResponse,
)
def get_lsp_references(
    session_id: str,
    path: str = Query(...),
    line: int = Query(..., ge=0),
    character: int = Query(..., ge=0),
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> LspReferencesResponse:
    sessions.get_session(session_id)
    try:
        result = agents.lsp_references(
            session_id, path=path, line=line, character=character
        )
    except LspError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return LspReferencesResponse(
        path=path,
        line=line,
        character=character,
        locations=[_loc_resp(loc) for loc in result.locations],
    )


@router.get(
    "/api/sessions/{session_id}/lsp/hover",
    response_model=LspHoverResponse,
)
def get_lsp_hover(
    session_id: str,
    path: str = Query(...),
    line: int = Query(..., ge=0),
    character: int = Query(..., ge=0),
    agents: AgentService = Depends(get_agent_service),
    sessions: SessionService = Depends(get_session_service),
) -> LspHoverResponse:
    sessions.get_session(session_id)
    try:
        result = agents.lsp_hover(
            session_id, path=path, line=line, character=character
        )
    except LspError as exc:
        raise InvalidSessionError(str(exc)) from exc
    return LspHoverResponse(
        path=path,
        line=line,
        character=character,
        contents=result.contents,
        range=_range_resp(result.range),
    )
