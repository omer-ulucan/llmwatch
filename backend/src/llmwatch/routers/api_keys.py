"""
Module: api_keys.py
Purpose: CRUD endpoints for managing API keys used for programmatic access.
WHY: API keys provide a stateless, long-lived alternative to JWT tokens for
machine-to-machine integrations (SDKs, CI pipelines, monitoring scripts).
The raw key is returned ONCE at creation time — only a SHA-256 hash is stored.
Managing keys requires a browser session (see get_session_user).
"""

import secrets
from typing import Any, Dict

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.auth.dependencies import get_session_user, hash_api_key
from llmwatch.config import logger
from llmwatch.db.engine import get_session
from llmwatch.db.models import ApiKey
from llmwatch.db.repository import WorkspaceRepository
from llmwatch.exceptions import ResourceNotFoundException
from llmwatch.models.schemas import (
    ApiKeyListResponse,
    ApiKeyResponse,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
)
from llmwatch.rate_limit import limiter

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


class ApiKeyRepository(WorkspaceRepository[ApiKey]):
    model = ApiKey


def _generate_raw_key() -> str:
    """Generate a raw API key with the lw_ prefix + 48 hex chars (24 random bytes).
    WHY: The prefix makes keys easily identifiable in logs and secret scanners.
    24 bytes of randomness = 192 bits of entropy — sufficient for API key security.
    """
    return f"lw_{secrets.token_hex(24)}"


def _hash_key(raw_key: str) -> str:
    """SHA-256 hash the raw key for storage.
    WHY: We never store the raw key. If the database is compromised,
    the attacker cannot recover usable API keys from the hashes.
    """
    return hash_api_key(raw_key)


def _new_key(raw_key: str, name: str, user_id: str) -> ApiKey:
    return ApiKey(
        name=name,
        user_id=user_id,
        key_hash=_hash_key(raw_key),
        prefix=raw_key[:10] + "...",  # "lw_" + first 7 hex chars + "..."
    )


def _created_response(key: ApiKey, raw_key: str) -> CreateApiKeyResponse:
    return CreateApiKeyResponse(
        key_id=key.id,
        name=key.name,
        raw_key=raw_key,
        prefix=key.prefix,
        created_at=key.created_at.isoformat(),
    )


async def _owned_key(repo: ApiKeyRepository, key_id: str) -> ApiKey:
    key = await repo.get(key_id)
    if key is None:
        # WHY: Same 404 for "doesn't exist" and "belongs to another workspace".
        raise ResourceNotFoundException(f"API key not found: {key_id}")
    return key


@router.post(
    "",
    response_model=CreateApiKeyResponse,
    status_code=201,
    summary="Create a new API key",
)
@limiter.limit("10/minute")
async def create_api_key(
    request: Request,
    body: CreateApiKeyRequest,
    current_user: Dict[str, Any] = Depends(get_session_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Creates a new API key for programmatic access.
    WHY: The raw key is returned in this response ONLY — it is never stored or
    retrievable again. The user must copy it immediately.
    """
    repo = ApiKeyRepository(session, current_user["workspace_id"])
    raw_key = _generate_raw_key()
    key = repo.add(_new_key(raw_key, body.name, current_user["user_id"]))
    await session.commit()

    logger.info(
        f"API key created: key_id={key.id} workspace={current_user['workspace_id']}"
    )
    return _created_response(key, raw_key)


@router.get("", response_model=ApiKeyListResponse, summary="List all API keys")
@limiter.limit("30/minute")
async def list_api_keys(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_session_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Returns all API keys for the authenticated user's workspace.
    WHY: The settings page needs to display key names, masked prefixes,
    usage stats, and provide revoke/regenerate controls.
    """
    repo = ApiKeyRepository(session, current_user["workspace_id"])
    keys = await repo.list(order_by=ApiKey.created_at.desc())
    return ApiKeyListResponse(
        keys=[
            ApiKeyResponse(
                key_id=k.id,
                name=k.name,
                prefix=k.prefix,
                created_at=k.created_at.isoformat(),
                last_used_at=k.last_used_at.isoformat() if k.last_used_at else None,
                request_count=k.request_count,
                is_active=k.is_active,
            )
            for k in keys
        ]
    )


@router.post(
    "/{key_id}/regenerate",
    response_model=CreateApiKeyResponse,
    summary="Regenerate an API key",
)
@limiter.limit("10/minute")
async def regenerate_api_key(
    request: Request,
    key_id: str,
    current_user: Dict[str, Any] = Depends(get_session_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Revokes the old key and issues a new one with the same name.
    WHY: Key rotation is a security best practice. Regenerating rather than
    just revoking lets users seamlessly update their integrations without
    needing to reconfigure the key name.
    """
    repo = ApiKeyRepository(session, current_user["workspace_id"])
    existing = await _owned_key(repo, key_id)

    raw_key = _generate_raw_key()
    new_key = repo.add(_new_key(raw_key, existing.name, current_user["user_id"]))
    await repo.delete(existing)
    await session.commit()

    logger.info(
        f"API key regenerated: old_key_id={key_id} new_key_id={new_key.id} "
        f"workspace={current_user['workspace_id']}"
    )
    return _created_response(new_key, raw_key)


@router.delete("/{key_id}", status_code=204, summary="Revoke an API key")
@limiter.limit("10/minute")
async def revoke_api_key(
    request: Request,
    key_id: str,
    current_user: Dict[str, Any] = Depends(get_session_user),
    session: AsyncSession = Depends(get_session),
):
    """
    Permanently revokes (hard-deletes) an API key.
    WHY: Hard delete ensures the key can never authenticate again.
    """
    repo = ApiKeyRepository(session, current_user["workspace_id"])
    key = await _owned_key(repo, key_id)
    await repo.delete(key)
    await session.commit()

    logger.info(
        f"API key revoked: key_id={key_id} workspace={current_user['workspace_id']}"
    )
    # 204 No Content — no response body
