"""Request/response schemas for the providers API (keys are never returned)."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from llmwatch.db.models import Provider
from llmwatch.providers.presets import get_preset
from llmwatch.security.crypto import mask_secret


class ProviderCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(..., min_length=1, max_length=100)
    preset: str = Field(..., min_length=1, max_length=40)
    # Defaults to the preset's URL when omitted.
    base_url: str | None = Field(None, max_length=500)
    api_key: str | None = Field(None, max_length=1000)
    enabled: bool = True


class ProviderUpdate(BaseModel):
    """Partial update. Omit api_key to keep it, send null or "" to remove it."""

    model_config = ConfigDict(extra="forbid")
    name: str | None = Field(None, min_length=1, max_length=100)
    base_url: str | None = Field(None, max_length=500)
    api_key: str | None = Field(None, max_length=1000)
    enabled: bool | None = None


class ProviderOut(BaseModel):
    id: str
    name: str
    preset: str
    preset_label: str
    base_url: str
    has_api_key: bool
    api_key_masked: str | None
    enabled: bool
    managed_by_env: bool
    local: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def of(cls, p: Provider) -> "ProviderOut":
        preset = get_preset(p.preset)
        has_key = p.api_key_encrypted is not None
        return cls(
            id=p.id,
            name=p.name,
            preset=p.preset,
            preset_label=preset.label,
            base_url=p.base_url,
            has_api_key=has_key,
            api_key_masked=mask_secret(p.api_key_hint) if has_key else None,
            enabled=p.enabled,
            managed_by_env=p.managed_by_env,
            local=preset.local,
            created_at=p.created_at,
            updated_at=p.updated_at,
        )


class ConnectionTestOut(BaseModel):
    ok: bool
    latency_ms: float
    model_count: int
    models: list[str]
    error: str | None = None
    error_kind: str | None = None


class DiscoverOut(BaseModel):
    discovered: list[str]
    added: list[str]


# ── Models ──────────────────────────────────────────────────


class Capabilities(BaseModel):
    tools: bool = False
    vision: bool = False
    reasoning: bool = False
    json_mode: bool = False


class ModelCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")
    provider_id: str
    model_id: str = Field(..., min_length=1, max_length=200)
    display_name: str | None = Field(None, max_length=200)
    context_window: int | None = Field(None, gt=0)
    capabilities: Capabilities = Capabilities()
    input_price_per_mtok: float | None = Field(None, ge=0)
    output_price_per_mtok: float | None = Field(None, ge=0)
    open_weights: bool = False
    is_default: bool = False
    enabled: bool = True


class ModelUpdate(BaseModel):
    """Partial update; send a price as null to mark the model unpriced."""

    model_config = ConfigDict(extra="forbid")
    display_name: str | None = Field(None, min_length=1, max_length=200)
    context_window: int | None = Field(None, gt=0)
    capabilities: Capabilities | None = None
    input_price_per_mtok: float | None = Field(None, ge=0)
    output_price_per_mtok: float | None = Field(None, ge=0)
    open_weights: bool | None = None
    is_default: bool | None = None
    enabled: bool | None = None


class ModelOut(BaseModel):
    id: str
    provider_id: str
    provider_name: str
    provider_preset: str
    model_id: str
    # "Provider name/model-id": accepted anywhere a model is expected.
    ref: str
    display_name: str
    context_window: int | None
    capabilities: Capabilities
    input_price_per_mtok: float | None
    output_price_per_mtok: float | None
    priced: bool
    open_weights: bool
    local: bool
    is_default: bool
    enabled: bool
    # False when the model or its provider is disabled.
    available: bool

    @classmethod
    def of(cls, m, p: Provider) -> "ModelOut":
        return cls(
            id=m.id,
            provider_id=p.id,
            provider_name=p.name,
            provider_preset=p.preset,
            model_id=m.model_id,
            ref=f"{p.name}/{m.model_id}",
            display_name=m.display_name,
            context_window=m.context_window,
            capabilities=Capabilities(
                tools=m.supports_tools,
                vision=m.supports_vision,
                reasoning=m.supports_reasoning,
                json_mode=m.supports_json,
            ),
            input_price_per_mtok=m.input_price_per_mtok,
            output_price_per_mtok=m.output_price_per_mtok,
            priced=m.input_price_per_mtok is not None
            or m.output_price_per_mtok is not None,
            open_weights=m.open_weights,
            local=get_preset(p.preset).local,
            is_default=m.is_default,
            enabled=m.enabled,
            available=m.enabled and p.enabled,
        )


class ModelGroup(BaseModel):
    provider: ProviderOut
    models: list[ModelOut]


class ModelCatalog(BaseModel):
    groups: list[ModelGroup]
    default_model_id: str | None
