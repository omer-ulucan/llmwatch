"""
Module: api_keys.py
Purpose: CRUD endpoints for managing API keys used for programmatic access.
WHY: API keys provide a stateless, long-lived alternative to JWT tokens for
machine-to-machine integrations (SDKs, CI pipelines, monitoring scripts).
The raw key is returned ONCE at creation time — only a SHA-256 hash is stored.
"""

import secrets
import hashlib
import uuid
from datetime import datetime, timezone
from typing import Dict, Any

from fastapi import APIRouter, Depends, Request
from config import logger
from auth.dependencies import get_current_user
from services.dynamo_service import get_dynamo_service
from models.schemas import (
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    ApiKeyResponse,
    ApiKeyListResponse,
)
from exceptions import ResourceNotFoundException
from rate_limit import limiter

router = APIRouter(prefix="/api-keys", tags=["API Keys"])


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
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _build_key_record(
    raw_key: str, name: str, user_id: str, company_id: str
) -> Dict[str, Any]:
    """Build the DynamoDB item for a new API key.
    WHY: Centralizes record construction to keep endpoint handlers clean
    and ensure consistent field population.
    """
    now = datetime.now(timezone.utc).isoformat()
    key_id = str(uuid.uuid4())
    key_hash = _hash_key(raw_key)
    prefix = raw_key[:10] + "..."  # "lw_" + first 7 hex chars + "..."

    return {
        "key_hash": key_hash,
        "key_id": key_id,
        "company_id": company_id,
        "user_id": user_id,
        "name": name,
        "prefix": prefix,
        "created_at": now,
        "last_used_at": None,
        "request_count": 0,
        "is_active": True,
    }


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
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Creates a new API key for programmatic access.
    WHY: The raw key is returned in this response ONLY — it is never stored or
    retrievable again. The user must copy it immediately.
    """
    raw_key = _generate_raw_key()
    record = _build_key_record(
        raw_key=raw_key,
        name=body.name,
        user_id=current_user["user_id"],
        company_id=current_user["company_id"],
    )

    db = get_dynamo_service()
    db.save_api_key(record)

    logger.info(
        f"API key created: key_id={record['key_id']} "
        f"company={current_user['company_id']}"
    )

    return CreateApiKeyResponse(
        key_id=record["key_id"],
        name=record["name"],
        raw_key=raw_key,
        prefix=record["prefix"],
        created_at=record["created_at"],
    )


@router.get("", response_model=ApiKeyListResponse, summary="List all API keys")
@limiter.limit("30/minute")
async def list_api_keys(
    request: Request,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Returns all API keys for the authenticated user's company.
    WHY: The settings page needs to display key names, masked prefixes,
    usage stats, and provide revoke/regenerate controls.
    """
    db = get_dynamo_service()
    items = db.get_api_keys_by_company(current_user["company_id"])

    keys = [
        ApiKeyResponse(
            key_id=item["key_id"],
            name=item["name"],
            prefix=item["prefix"],
            created_at=item["created_at"],
            last_used_at=item.get("last_used_at"),
            request_count=int(item.get("request_count", 0)),
            is_active=item.get("is_active", True),
        )
        for item in items
    ]

    return ApiKeyListResponse(keys=keys)


@router.post(
    "/{key_id}/regenerate",
    response_model=CreateApiKeyResponse,
    summary="Regenerate an API key",
)
@limiter.limit("10/minute")
async def regenerate_api_key(
    request: Request,
    key_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Revokes the old key and issues a new one with the same name.
    WHY: Key rotation is a security best practice. Regenerating rather than
    just revoking lets users seamlessly update their integrations without
    needing to reconfigure the key name.
    """
    db = get_dynamo_service()

    # Find existing key (verifies company ownership)
    existing = db.get_api_key_by_id(current_user["company_id"], key_id)
    if not existing:
        raise ResourceNotFoundException(f"API key not found: {key_id}")

    # Delete the old key
    db.delete_api_key(existing["key_hash"])

    # Create new key with same name
    raw_key = _generate_raw_key()
    record = _build_key_record(
        raw_key=raw_key,
        name=existing["name"],
        user_id=current_user["user_id"],
        company_id=current_user["company_id"],
    )
    db.save_api_key(record)

    logger.info(
        f"API key regenerated: old_key_id={key_id} new_key_id={record['key_id']} "
        f"company={current_user['company_id']}"
    )

    return CreateApiKeyResponse(
        key_id=record["key_id"],
        name=record["name"],
        raw_key=raw_key,
        prefix=record["prefix"],
        created_at=record["created_at"],
    )


@router.delete("/{key_id}", status_code=204, summary="Revoke an API key")
@limiter.limit("10/minute")
async def revoke_api_key(
    request: Request,
    key_id: str,
    current_user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Permanently revokes (hard-deletes) an API key.
    WHY: Hard delete ensures the key can never authenticate again.
    Soft delete would require checking is_active on every auth request,
    adding latency and complexity with no real benefit for API keys.
    """
    db = get_dynamo_service()

    existing = db.get_api_key_by_id(current_user["company_id"], key_id)
    if not existing:
        raise ResourceNotFoundException(f"API key not found: {key_id}")

    db.delete_api_key(existing["key_hash"])

    logger.info(
        f"API key revoked: key_id={key_id} company={current_user['company_id']}"
    )
    # 204 No Content — no response body
