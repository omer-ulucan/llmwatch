"""
Module: dependencies.py
Purpose: FastAPI dependencies for enforcing Authentication via JWT or API Key.
WHY: Using dependency injection separates routing from security validation, keeping controllers clean.
Supports two auth methods:
  1. Bearer JWT token (for browser sessions)
  2. X-API-Key header (for programmatic/SDK access)

Both resolve to the same user context dict:
  user_id, workspace_id, role, email, auth_method ("jwt" | "api_key"), api_key_id.
The user row is loaded on every request, so deactivated users and deleted
workspaces lose access immediately instead of when their token expires.
"""

import hashlib
from datetime import UTC, datetime
from typing import Any, Dict, Optional

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.auth.jwt_handler import decode_access_token
from llmwatch.db.engine import get_session
from llmwatch.db.models import ApiKey, User
from llmwatch.exceptions import AuthenticationException, AuthorizationException

# WHY: OAuth2PasswordBearer automatically looks for the Authorization: Bearer <token> header
# and integrates directly with FastAPI's OpenAPI swagger documentation standard.
# tokenUrl points to the form-encoded /auth/token endpoint (not the JSON /auth/login)
# because Swagger UI sends application/x-www-form-urlencoded per the OAuth2 spec.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token", auto_error=False)


def hash_api_key(raw_key: str) -> str:
    """SHA-256 hex digest used to store and look up API keys."""
    return hashlib.sha256(raw_key.encode()).hexdigest()


def _context(
    user: User | None, workspace_id: str, auth_method: str, **extra
) -> Dict[str, Any]:
    return {
        "user_id": user.id if user else None,
        "workspace_id": workspace_id,
        "role": user.role if user else "member",
        "email": user.email if user else None,
        "auth_method": auth_method,
        "api_key_id": None,
        **extra,
    }


async def _authenticate_via_api_key(
    raw_key: str, session: AsyncSession
) -> Dict[str, Any]:
    """
    Validates an API key by hashing it and looking up the hash.
    WHY: Hash lookup is fast and avoids storing the raw key.

    Raises:
        AuthenticationException: If the key is invalid, inactive, or not found.
    """
    key_hash = hash_api_key(raw_key)
    key = (
        await session.execute(select(ApiKey).where(ApiKey.key_hash == key_hash))
    ).scalar_one_or_none()
    if key is None:
        raise AuthenticationException("Invalid API key")
    if not key.is_active:
        raise AuthenticationException("API key has been revoked")

    user = await session.get(User, key.user_id) if key.user_id else None
    if user is not None and not user.is_active:
        raise AuthenticationException("Account disabled")

    # Usage tracking: one UPDATE, done atomically in the database.
    await session.execute(
        update(ApiKey)
        .where(ApiKey.id == key.id)
        .values(request_count=ApiKey.request_count + 1, last_used_at=datetime.now(UTC))
    )
    await session.commit()

    ctx = _context(user, key.workspace_id, "api_key", api_key_id=key.id)
    if user is None:
        # The key outlived its creator; it keeps member-level access to the workspace.
        ctx["role"] = "member"
    return ctx


async def _authenticate_via_jwt(
    token: Optional[str], session: AsyncSession
) -> Dict[str, Any]:
    if not token:
        raise AuthenticationException("Not authenticated")

    payload = decode_access_token(token)
    user = await session.get(User, str(payload["sub"]))
    if user is None:
        raise AuthenticationException("Could not validate credentials")
    if not user.is_active:
        raise AuthenticationException("Account disabled")
    return _context(user, user.workspace_id, "jwt")


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    Validates authentication via API key or JWT token and returns user context.
    WHY: Supporting both auth methods allows the same protected endpoints to serve
    both browser sessions (JWT) and programmatic clients (API key) without
    requiring separate endpoint sets.

    Priority:
      1. X-API-Key header (checked first — programmatic clients)
      2. Authorization: Bearer <JWT> (fallback — browser sessions)

    Raises:
        AuthenticationException: If neither auth method provides valid credentials.
    """
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return await _authenticate_via_api_key(api_key, session)
    return await _authenticate_via_jwt(token, session)


async def get_session_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
    session: AsyncSession = Depends(get_session),
) -> Dict[str, Any]:
    """
    Like get_current_user, but only accepts a browser session (JWT).
    WHY: Used for credential and workspace management. If API keys could create,
    rotate or delete API keys, one leaked key could mint replacements and revoke the
    owner's keys, keeping access after the leak is noticed.

    Raises:
        AuthorizationException: If the request carries an X-API-Key header.
        AuthenticationException: If there is no valid JWT.
    """
    if request.headers.get("X-API-Key"):
        raise AuthorizationException(
            "This action needs a signed-in session; API keys can't be used for it"
        )
    return await _authenticate_via_jwt(token, session)


async def require_owner(
    current_user: Dict[str, Any] = Depends(get_session_user),
) -> Dict[str, Any]:
    """Session user who owns the workspace (for destructive workspace actions)."""
    if current_user["role"] != "owner":
        raise AuthorizationException("Only the workspace owner can do this")
    return current_user
