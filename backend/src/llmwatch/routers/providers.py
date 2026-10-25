"""
Module: providers.py
Purpose: Manage the workspace's LLM providers (presets, keys, connection checks).
WHY: Providers are configured per workspace in the UI. Reading is open to every
member; creating, editing, deleting and model discovery need the workspace owner in
a browser session, since they control where the workspace's keys are sent.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.auth.dependencies import get_current_user, require_owner
from llmwatch.config import logger
from llmwatch.db.engine import get_session
from llmwatch.db.models import Provider
from llmwatch.exceptions import ResourceNotFoundException, ValidationException
from llmwatch.providers import service
from llmwatch.providers.presets import PRESETS
from llmwatch.providers.schemas import (
    ConnectionTestOut,
    DiscoverOut,
    ProviderCreate,
    ProviderOut,
    ProviderUpdate,
)
from llmwatch.rate_limit import limiter

router = APIRouter(prefix="/providers", tags=["Providers"])


async def _get(session: AsyncSession, workspace_id: str, provider_id: str) -> Provider:
    provider = await service.ProviderRepository(session, workspace_id).get(provider_id)
    if provider is None:
        raise ResourceNotFoundException("Provider not found")
    return provider


@router.get("/presets")
async def list_presets(current_user: Dict[str, Any] = Depends(get_current_user)):
    return {"presets": [p.to_dict() for p in PRESETS.values()]}


@router.get("", response_model=list[ProviderOut])
async def list_providers(
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    repo = service.ProviderRepository(session, current_user["workspace_id"])
    return [ProviderOut.of(p) for p in await repo.list(order_by=Provider.name)]


@router.post("", response_model=ProviderOut, status_code=201)
@limiter.limit("30/minute")
async def create_provider(
    request: Request,
    body: ProviderCreate,
    current_user: Dict[str, Any] = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
):
    repo = service.ProviderRepository(session, current_user["workspace_id"])
    provider = await service.create_provider(
        repo,
        name=body.name.strip(),
        preset=body.preset,
        base_url=body.base_url,
        api_key=body.api_key,
        enabled=body.enabled,
    )
    await session.commit()
    logger.info(
        f"Provider created: id={provider.id} preset={provider.preset} "
        f"workspace={current_user['workspace_id']}"
    )
    return ProviderOut.of(provider)


@router.get("/{provider_id}", response_model=ProviderOut)
async def get_provider(
    provider_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    return ProviderOut.of(
        await _get(session, current_user["workspace_id"], provider_id)
    )


@router.patch("/{provider_id}", response_model=ProviderOut)
@limiter.limit("30/minute")
async def update_provider(
    request: Request,
    provider_id: str,
    body: ProviderUpdate,
    current_user: Dict[str, Any] = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
):
    provider = await _get(session, current_user["workspace_id"], provider_id)
    repo = service.ProviderRepository(session, current_user["workspace_id"])
    kwargs: dict[str, Any] = {
        "name": body.name.strip() if body.name else None,
        "base_url": body.base_url,
        "enabled": body.enabled,
    }
    if "api_key" in body.model_fields_set:
        kwargs["api_key"] = body.api_key
    await service.update_provider(repo, provider, **kwargs)
    await session.commit()
    return ProviderOut.of(provider)


@router.delete("/{provider_id}", status_code=204)
@limiter.limit("30/minute")
async def delete_provider(
    request: Request,
    provider_id: str,
    current_user: Dict[str, Any] = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
):
    provider = await _get(session, current_user["workspace_id"], provider_id)
    if provider.managed_by_env:
        raise ValidationException(
            "This provider is configured through environment variables; remove the "
            "variable (or disable the provider) instead"
        )
    await service.ProviderRepository(session, current_user["workspace_id"]).delete(
        provider
    )
    await session.commit()
    return Response(status_code=204)


@router.post("/{provider_id}/test", response_model=ConnectionTestOut)
@limiter.limit("20/minute")
async def test_provider(
    request: Request,
    provider_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    provider = await _get(session, current_user["workspace_id"], provider_id)
    result = await service.test_connection(provider)
    return ConnectionTestOut(
        ok=result.ok,
        latency_ms=round(result.latency_ms, 1),
        model_count=len(result.models),
        models=result.models[:200],
        error=result.error,
        error_kind=result.error_kind,
    )


@router.post("/{provider_id}/discover", response_model=DiscoverOut)
@limiter.limit("10/minute")
async def discover_models(
    request: Request,
    provider_id: str,
    current_user: Dict[str, Any] = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
):
    """Imports the models the provider lists (GET /models) into the workspace."""
    provider = await _get(session, current_user["workspace_id"], provider_id)
    result = await service.test_connection(provider)
    if not result.ok:
        raise ValidationException(f"Could not list models: {result.error}")
    added = await service.discover_models(session, provider, result.models)
    await session.commit()
    return DiscoverOut(discovered=result.models, added=added)
