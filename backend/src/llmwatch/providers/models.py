"""
Module: models.py
Purpose: The workspace's model catalogue and resolving a model reference to a client.
WHY: Chat, the agent and evals all take a "model" string. It may be a model's id, a
"Provider/model-id" pair, a bare provider model id, "default", or one of the legacy
aliases ("qwen", "gemini") older API clients still send. Resolving that in one place
gives every caller the same rules and the same clear error when nothing matches.
"""

from dataclasses import dataclass

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.config import settings
from llmwatch.db.models import Model, Provider
from llmwatch.db.repository import WorkspaceRepository
from llmwatch.exceptions import ValidationException
from llmwatch.llm import LLMClient
from llmwatch.providers import service as provider_service

LEGACY_ALIASES = ("qwen", "gemini")


class ModelRepository(WorkspaceRepository[Model]):
    model = Model

    async def with_providers(self, *where) -> list[tuple[Model, Provider]]:
        stmt = (
            select(Model, Provider)
            .join(Provider, Provider.id == Model.provider_id)
            .where(Model.workspace_id == self.workspace_id, *where)
            .order_by(Provider.name, Model.display_name)
        )
        return [(m, p) for m, p in (await self.session.execute(stmt)).all()]

    async def set_default(self, model: Model) -> None:
        # WHY: Clear first, then set, so the partial unique index never sees two.
        await self.session.execute(
            update(Model)
            .where(Model.workspace_id == self.workspace_id, Model.id != model.id)
            .values(is_default=False)
        )
        await self.session.flush()
        model.is_default = True
        await self.session.flush()


@dataclass
class ResolvedModel:
    model: Model
    provider: Provider

    @property
    def label(self) -> str:
        return f"{self.provider.name}/{self.model.model_id}"

    def client(self) -> LLMClient:
        return provider_service.client_for(self.provider)


def _usable(model: Model, provider: Provider) -> bool:
    return model.enabled and provider.enabled


async def resolve_model(
    session: AsyncSession, workspace_id: str, ref: str
) -> ResolvedModel:
    """
    Finds an enabled model for `ref`, or raises ValidationException (HTTP 400).

    Accepted forms, in order: a model row id; "default"; a legacy alias; the
    "Provider name/model-id" pair; a provider model id that is unique in the
    workspace.
    """
    ref = (ref or "").strip()
    if not ref:
        raise ValidationException("model is required")
    rows = [
        (m, p)
        for m, p in await ModelRepository(session, workspace_id).with_providers()
        if _usable(m, p)
    ]

    for m, p in rows:
        if m.id == ref:
            return ResolvedModel(m, p)

    if ref == "default":
        for m, p in rows:
            if m.is_default:
                return ResolvedModel(m, p)
        raise ValidationException(
            "No default model is set; pick one on the Models page"
        )

    if ref in LEGACY_ALIASES:
        found = _resolve_legacy(ref, rows)
        if found is not None:
            return found
        raise ValidationException(
            f"Model alias {ref!r} isn't configured in this workspace. Add a "
            + (
                "Gemini provider and model"
                if ref == "gemini"
                else "vLLM provider serving Qwen"
            )
            + " on the Models page, or send a model id."
        )

    if "/" in ref:
        provider_name, _, model_id = ref.partition("/")
        for m, p in rows:
            if p.name == provider_name and m.model_id == model_id:
                return ResolvedModel(m, p)

    matches = [(m, p) for m, p in rows if m.model_id == ref]
    if len(matches) == 1:
        return ResolvedModel(*matches[0])
    if len(matches) > 1:
        names = ", ".join(f"{p.name}/{m.model_id}" for m, p in matches)
        raise ValidationException(
            f"Model {ref!r} is offered by several providers; use one of: {names}"
        )
    raise ValidationException(f"Unknown or disabled model: {ref!r}")


def _resolve_legacy(
    alias: str, rows: list[tuple[Model, Provider]]
) -> ResolvedModel | None:
    if alias == "gemini":
        candidates = [(m, p) for m, p in rows if p.preset == "gemini"]
        preferred = settings.gemini_model
    else:
        candidates = [(m, p) for m, p in rows if p.preset == "vllm"]
        preferred = settings.qwen_model
        # The provider seeded from QWEN_BASE_URL wins over other vLLM servers.
        named = [(m, p) for m, p in candidates if p.name == "Qwen (vLLM)"]
        candidates = named or candidates
    if not candidates:
        return None
    for m, p in candidates:
        if m.model_id == preferred:
            return ResolvedModel(m, p)
    for m, p in candidates:
        if m.is_default:
            return ResolvedModel(m, p)
    return ResolvedModel(*candidates[0])


# ── Env seeding of the legacy alias models ──────────────────

# WHY: Prices the original "gemini" alias used (USD per 1M tokens). Editable on the
# Models page; check your provider's current pricing.
LEGACY_GEMINI_PRICES = (0.50, 3.00)


async def seed_legacy_models(session: AsyncSession, workspace_id: str) -> None:
    """Gives env-seeded Gemini / Qwen providers the model the old aliases used, so
    "gemini" and "qwen" keep working right after an upgrade."""
    providers = await provider_service.ProviderRepository(session, workspace_id).list(
        Provider.managed_by_env.is_(True)
    )
    for provider in providers:
        if provider.preset == "gemini":
            spec = (settings.gemini_model, LEGACY_GEMINI_PRICES, False, True)
        elif provider.name == "Qwen (vLLM)":
            # $0.0001 per 1K tokens, as the old "qwen" alias charged.
            spec = (settings.qwen_model, (0.10, 0.10), True, True)
        else:
            continue
        model_id, (price_in, price_out), open_weights, reasoning = spec
        exists = (
            await session.execute(
                select(Model.id).where(
                    Model.provider_id == provider.id, Model.model_id == model_id
                )
            )
        ).first()
        if exists:
            continue
        session.add(
            Model(
                workspace_id=workspace_id,
                provider_id=provider.id,
                model_id=model_id,
                display_name=model_id,
                input_price_per_mtok=price_in,
                output_price_per_mtok=price_out,
                open_weights=open_weights,
                supports_reasoning=reasoning,
            )
        )
    await session.flush()
