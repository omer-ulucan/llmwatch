"""
Module: models.py (router)
Purpose: The workspace's model catalogue: metadata, prices, capabilities, default.
WHY: Every model picker (chat, agent, evals) reads GET /models; owners maintain the
catalogue. Prices drive every cost figure, so they are explicit and editable, and an
unknown price is shown as unpriced rather than $0.
"""

from typing import Any, Dict

from fastapi import APIRouter, Depends, Request, Response
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.auth.dependencies import get_current_user, require_owner
from llmwatch.db.engine import get_session
from llmwatch.db.models import Model, Provider
from llmwatch.exceptions import (
    ConflictException,
    ResourceNotFoundException,
)
from llmwatch.providers.models import ModelRepository, resolve_model
from llmwatch.providers.presets import get_preset
from llmwatch.providers.schemas import (
    ModelCatalog,
    ModelCreate,
    ModelGroup,
    ModelOut,
    ModelUpdate,
    ProviderOut,
)
from llmwatch.providers.service import ProviderRepository
from llmwatch.rate_limit import limiter

router = APIRouter(prefix="/models", tags=["Models"])


async def _get(session: AsyncSession, workspace_id: str, model_id: str):
    repo = ModelRepository(session, workspace_id)
    for m, p in await repo.with_providers(Model.id == model_id):
        return repo, m, p
    raise ResourceNotFoundException("Model not found")


@router.get("", response_model=ModelCatalog)
async def list_models(
    available_only: bool = False,
    open_weights: bool | None = None,
    local: bool | None = None,
    q: str | None = None,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Models grouped by provider. Pickers pass available_only=true; filters for
    open-weights and local models, and a case-insensitive search on names.
    """
    rows = await ModelRepository(session, current_user["workspace_id"]).with_providers()
    groups: dict[str, ModelGroup] = {}
    default_id = None
    needle = (q or "").lower().strip()
    for m, p in rows:
        if m.is_default:
            default_id = m.id
        if available_only and not (m.enabled and p.enabled):
            continue
        if open_weights is not None and m.open_weights != open_weights:
            continue
        if local is not None and get_preset(p.preset).local != local:
            continue
        if needle and not any(
            needle in s.lower() for s in (m.model_id, m.display_name, p.name)
        ):
            continue
        group = groups.setdefault(
            p.id, ModelGroup(provider=ProviderOut.of(p), models=[])
        )
        group.models.append(ModelOut.of(m, p))
    return ModelCatalog(groups=list(groups.values()), default_model_id=default_id)


@router.get("/resolve", response_model=ModelOut)
async def resolve(
    ref: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    """What a model reference (id, alias, "Provider/model", "default") points to."""
    resolved = await resolve_model(session, current_user["workspace_id"], ref)
    return ModelOut.of(resolved.model, resolved.provider)


@router.post("", response_model=ModelOut, status_code=201)
@limiter.limit("60/minute")
async def create_model(
    request: Request,
    body: ModelCreate,
    current_user: Dict[str, Any] = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
):
    workspace_id = current_user["workspace_id"]
    provider: Provider | None = await ProviderRepository(session, workspace_id).get(
        body.provider_id
    )
    if provider is None:
        raise ResourceNotFoundException("Provider not found")
    repo = ModelRepository(session, workspace_id)
    if await repo.list(
        Model.provider_id == provider.id, Model.model_id == body.model_id
    ):
        raise ConflictException(f"{provider.name} already has model {body.model_id!r}")

    model = repo.add(
        Model(
            provider_id=provider.id,
            model_id=body.model_id,
            display_name=body.display_name or body.model_id,
            context_window=body.context_window,
            supports_tools=body.capabilities.tools,
            supports_vision=body.capabilities.vision,
            supports_reasoning=body.capabilities.reasoning,
            supports_json=body.capabilities.json_mode,
            input_price_per_mtok=body.input_price_per_mtok,
            output_price_per_mtok=body.output_price_per_mtok,
            open_weights=body.open_weights,
            enabled=body.enabled,
        )
    )
    await session.flush()
    if body.is_default:
        await repo.set_default(model)
    await session.commit()
    return ModelOut.of(model, provider)


@router.patch("/{model_id}", response_model=ModelOut)
@limiter.limit("60/minute")
async def update_model(
    request: Request,
    model_id: str,
    body: ModelUpdate,
    current_user: Dict[str, Any] = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
):
    repo, model, provider = await _get(session, current_user["workspace_id"], model_id)
    fields = body.model_fields_set
    if "display_name" in fields and body.display_name:
        model.display_name = body.display_name
    if "context_window" in fields:
        model.context_window = body.context_window
    if "capabilities" in fields and body.capabilities is not None:
        model.supports_tools = body.capabilities.tools
        model.supports_vision = body.capabilities.vision
        model.supports_reasoning = body.capabilities.reasoning
        model.supports_json = body.capabilities.json_mode
    # Prices may be set to null on purpose (unpriced).
    if "input_price_per_mtok" in fields:
        model.input_price_per_mtok = body.input_price_per_mtok
    if "output_price_per_mtok" in fields:
        model.output_price_per_mtok = body.output_price_per_mtok
    if body.open_weights is not None:
        model.open_weights = body.open_weights
    if body.enabled is not None:
        model.enabled = body.enabled
        if not body.enabled:
            model.is_default = False
    if body.is_default is True:
        await repo.set_default(model)
    elif body.is_default is False:
        model.is_default = False
    await session.commit()
    return ModelOut.of(model, provider)


@router.delete("/{model_id}", status_code=204)
@limiter.limit("60/minute")
async def delete_model(
    request: Request,
    model_id: str,
    current_user: Dict[str, Any] = Depends(require_owner),
    session: AsyncSession = Depends(get_session),
):
    repo, model, _ = await _get(session, current_user["workspace_id"], model_id)
    await repo.delete(model)
    await session.commit()
    return Response(status_code=204)
