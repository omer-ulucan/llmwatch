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
