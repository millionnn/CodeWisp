"""Provider / Model 列表 REST（Web UI 共用 Registry）。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from backend.app.api.deps import AppState, get_app_state
from backend.app.api.schemas import ModelResponse, ProviderResponse

router = APIRouter(prefix="/api", tags=["providers"])


@router.get("/providers", response_model=list[ProviderResponse])
def list_providers(
    state: AppState = Depends(get_app_state),
) -> list[ProviderResponse]:
    resolver = state.model_resolver
    out: list[ProviderResponse] = []
    for p in resolver.providers.list():
        models = resolver.models.list_for_provider(p.provider_id)
        out.append(
            ProviderResponse(
                provider_id=p.provider_id,
                display_name=p.display_name,
                capabilities=sorted(p.capabilities),
                model_ids=[m.model_id for m in models],
                credential_configured=resolver.is_credential_configured(p.provider_id),
            )
        )
    return out


@router.get("/models", response_model=list[ModelResponse])
def list_models(
    provider_id: str | None = Query(default=None),
    state: AppState = Depends(get_app_state),
) -> list[ModelResponse]:
    resolver = state.model_resolver
    models = (
        resolver.models.list_for_provider(provider_id)
        if provider_id
        else resolver.models.list()
    )
    return [
        ModelResponse(
            model_id=m.model_id,
            provider_id=m.provider_id,
            display_name=m.display_name,
            context_window=m.context_window,
            supports_tool_call=m.supports_tool_call,
            supports_streaming=m.supports_streaming,
        )
        for m in models
    ]
