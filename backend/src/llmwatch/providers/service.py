"""
Module: service.py
Purpose: Provider persistence, key handling, connection checks and env seeding.
WHY: Keeps the rules about provider secrets in one place:
  - keys are encrypted at rest and only decrypted to call the provider
  - changing a provider's base URL drops its stored key unless a new key is given,
    otherwise anyone allowed to edit the provider could point it at their own
    server and capture the key with "test connection"
  - providers configured through environment variables are re-synced at startup
"""

import time
from dataclasses import dataclass
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.config import logger, settings
from llmwatch.db.models import Model, Provider, Workspace
from llmwatch.db.repository import WorkspaceRepository
from llmwatch.exceptions import ConflictException, ValidationException
from llmwatch.llm import LLMClient, LLMError, ProviderConfig
from llmwatch.providers.presets import PRESETS, get_preset
from llmwatch.security.crypto import (
    SecretDecryptionError,
    decrypt_secret,
    encrypt_secret,
    secret_hint,
)
from llmwatch.security.ssrf import BlockedURLError, ensure_public_host


class ProviderRepository(WorkspaceRepository[Provider]):
    model = Provider

    async def by_name(self, name: str) -> Provider | None:
        stmt = self.select().where(Provider.name == name)
        return (await self.session.execute(stmt)).scalar_one_or_none()


# ── URLs ────────────────────────────────────────────────────


async def validate_base_url(url: str, *, trusted: bool = False) -> str:
    """Checks a provider base URL. `trusted` skips the private-address policy
    (for URLs set by the operator through environment variables)."""
    url = url.strip()
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https") or not parsed.hostname:
        raise ValidationException("base_url must be an http(s) URL")
    if parsed.username or parsed.password:
        raise ValidationException("Put credentials in api_key, not in base_url")
    if not trusted and not settings.provider_allow_private_urls:
        port = parsed.port or (443 if parsed.scheme == "https" else 80)
        try:
            await ensure_public_host(parsed.hostname, port)
        except BlockedURLError as exc:
            raise ValidationException(
                f"base_url is not allowed on this server: {exc}"
            ) from exc
    return url


# ── Keys ────────────────────────────────────────────────────


def set_api_key(provider: Provider, api_key: str | None) -> None:
    if api_key:
        provider.api_key_encrypted = encrypt_secret(api_key)
        provider.api_key_hint = secret_hint(api_key)
    else:
        provider.api_key_encrypted = None
        provider.api_key_hint = None


def provider_config(provider: Provider) -> ProviderConfig:
    """Connection settings with the decrypted key.

    Raises:
        SecretDecryptionError: The stored key can't be decrypted.
    """
    api_key = (
        decrypt_secret(provider.api_key_encrypted)
        if provider.api_key_encrypted
        else None
    )
    preset = get_preset(provider.preset)
    return ProviderConfig(
        name=provider.name,
        base_url=provider.base_url,
        api_key=api_key,
        preset=provider.preset,
        stream_usage=preset.stream_usage,
    )


def make_client(config: ProviderConfig) -> LLMClient:
    """Builds the client for a provider (tests swap this for a fake)."""
    return LLMClient(config)


def client_for(provider: Provider) -> LLMClient:
    return make_client(provider_config(provider))


# ── CRUD ────────────────────────────────────────────────────


async def create_provider(
    repo: ProviderRepository,
    *,
    name: str,
    preset: str,
    base_url: str | None,
    api_key: str | None,
    enabled: bool = True,
    managed_by_env: bool = False,
) -> Provider:
    trusted_url = managed_by_env
    if preset not in PRESETS:
        raise ValidationException(f"Unknown preset: {preset}")
    url = base_url or PRESETS[preset].base_url
    if not url:
        raise ValidationException("base_url is required for custom providers")
    url = await validate_base_url(url, trusted=trusted_url)
    if await repo.by_name(name):
        raise ConflictException(f"A provider named {name!r} already exists")

    provider = Provider(
        name=name,
        preset=preset,
        base_url=url,
        enabled=enabled,
        managed_by_env=managed_by_env,
    )
    set_api_key(provider, api_key)
    repo.add(provider)
    await repo.session.flush()
    return provider


_UNSET = object()


async def update_provider(
    repo: ProviderRepository,
    provider: Provider,
    *,
    name: str | None = None,
    base_url: str | None = None,
    api_key: object = _UNSET,
    enabled: bool | None = None,
) -> Provider:
    """
    Partial update. api_key: _UNSET keeps the key, "" or None clears it, a string
    replaces it.
    """
    if provider.managed_by_env and (
        name is not None or base_url is not None or api_key is not _UNSET
    ):
        raise ValidationException(
            "This provider is configured through environment variables; only "
            "`enabled` can be changed here"
        )
    if name is not None and name != provider.name:
        if await repo.by_name(name):
            raise ConflictException(f"A provider named {name!r} already exists")
        provider.name = name
    if base_url is not None:
        new_url = await validate_base_url(base_url)
        if new_url != provider.base_url:
            provider.base_url = new_url
            if api_key is _UNSET and provider.api_key_encrypted:
                # WHY: Never send a stored key to a URL it wasn't entered for.
                set_api_key(provider, None)
                logger.info(
                    f"Provider {provider.id}: base_url changed, stored API key cleared"
                )
    if api_key is not _UNSET:
        set_api_key(provider, api_key or None)  # type: ignore[arg-type]
    if enabled is not None:
        provider.enabled = enabled
    await repo.session.flush()
    return provider


# ── Connection checks ───────────────────────────────────────


@dataclass
class ConnectionResult:
    ok: bool
    latency_ms: float
    models: list[str]
    error: str | None = None
    error_kind: str | None = None


async def test_connection(provider: Provider) -> ConnectionResult:
    """Lists models: proves the URL and key work without spending tokens."""
    started = time.perf_counter()
    try:
        client = client_for(provider)
        models = await client.list_models()
    except SecretDecryptionError as exc:
        return ConnectionResult(False, 0.0, [], str(exc), "decryption")
    except LLMError as exc:
        return ConnectionResult(
            False,
            (time.perf_counter() - started) * 1000,
            [],
            exc.message,
            exc.kind,
        )
    return ConnectionResult(True, (time.perf_counter() - started) * 1000, models)


async def discover_models(
    session: AsyncSession, provider: Provider, model_ids: list[str]
) -> list[str]:
    """Adds models the provider lists but the workspace doesn't have yet."""
    existing = set(
        (
            await session.execute(
                select(Model.model_id).where(Model.provider_id == provider.id)
            )
        ).scalars()
    )
    added = []
    preset = get_preset(provider.preset)
    for model_id in model_ids:
        if model_id in existing:
            continue
        session.add(
            Model(
                workspace_id=provider.workspace_id,
                provider_id=provider.id,
                model_id=model_id,
                display_name=model_id,
                # Self-hosted models cost nothing per token by default.
                input_price_per_mtok=0.0 if preset.local else None,
                output_price_per_mtok=0.0 if preset.local else None,
                open_weights=preset.local,
            )
        )
        added.append(model_id)
    await session.flush()
    return added


# ── Environment seeding ─────────────────────────────────────


@dataclass(frozen=True)
class EnvProvider:
    name: str
    preset: str
    base_url: str
    api_key: str | None
    env_var: str


def env_providers() -> list[EnvProvider]:
    """Providers described by the current environment variables."""
    found = []

    def keyed(env_var: str, preset: str, key: str):
        if key:
            p = PRESETS[preset]
            found.append(EnvProvider(p.label, preset, p.base_url, key, env_var))

    keyed("OPENAI_API_KEY", "openai", settings.openai_api_key)
    keyed("GOOGLE_API_KEY", "gemini", settings.google_api_key)
    keyed("OPENROUTER_API_KEY", "openrouter", settings.openrouter_api_key)
    keyed("GROQ_API_KEY", "groq", settings.groq_api_key)
    keyed("TOGETHER_API_KEY", "together", settings.together_api_key)
    if settings.ollama_base_url:
        found.append(
            EnvProvider(
                "Ollama", "ollama", settings.ollama_base_url, None, "OLLAMA_BASE_URL"
            )
        )
    if settings.vllm_base_url:
        found.append(
            EnvProvider(
                "vLLM",
                "vllm",
                settings.vllm_base_url,
                settings.vllm_api_key or None,
                "VLLM_BASE_URL",
            )
        )
    if settings.qwen_base_url:
        # Legacy name for a self-hosted vLLM serving Qwen.
        found.append(
            EnvProvider(
                "Qwen (vLLM)",
                "vllm",
                settings.qwen_base_url,
                settings.qwen_api_key or None,
                "QWEN_BASE_URL",
            )
        )
    return found


async def sync_env_providers(session: AsyncSession, workspace_id: str) -> None:
    """Creates/updates env-managed providers; disables ones whose env var is gone."""
    repo = ProviderRepository(session, workspace_id)
    wanted = {p.name: p for p in env_providers()}
    managed = await repo.list(Provider.managed_by_env.is_(True))

    for provider in managed:
        spec = wanted.pop(provider.name, None)
        if spec is None:
            provider.enabled = False
            continue
        provider.base_url = spec.base_url
        provider.preset = spec.preset
        current = None
        if provider.api_key_encrypted:
            try:
                current = decrypt_secret(provider.api_key_encrypted)
            except SecretDecryptionError:
                current = None
        if current != spec.api_key:
            set_api_key(provider, spec.api_key)

    for spec in wanted.values():
        existing = await repo.by_name(spec.name)
        if existing is not None:
            # A user-created provider already uses this name; leave it alone.
            logger.warning(
                f"Not seeding provider from {spec.env_var}: workspace "
                f"{workspace_id} already has a provider named {spec.name!r}"
            )
            continue
        await create_provider(
            repo,
            name=spec.name,
            preset=spec.preset,
            base_url=spec.base_url,
            api_key=spec.api_key,
            managed_by_env=True,
        )
    await session.flush()


async def sync_env_providers_all(session: AsyncSession) -> None:
    workspace_ids = (await session.execute(select(Workspace.id))).scalars().all()
    for workspace_id in workspace_ids:
        await sync_env_providers(session, workspace_id)
    await session.commit()
