"""
Module: dependencies.py
Purpose: FastAPI dependencies for enforcing Authentication via JWT or API Key.
WHY: Using dependency injection separates routing from security validation, keeping controllers clean.
Supports two auth methods:
  1. Bearer JWT token (for browser sessions)
  2. X-API-Key header (for programmatic/SDK access)
"""

import asyncio
import hashlib
from typing import Any, Dict, Optional

from fastapi import Depends, Request
from fastapi.security import OAuth2PasswordBearer

from auth.jwt_handler import decode_access_token
from config import logger
from exceptions import AuthenticationException, AuthorizationException

# WHY: OAuth2PasswordBearer automatically looks for the Authorization: Bearer <token> header
# and integrates directly with FastAPI's OpenAPI swagger documentation standard.
# tokenUrl points to the form-encoded /auth/token endpoint (not the JSON /auth/login)
# because Swagger UI sends application/x-www-form-urlencoded per the OAuth2 spec.
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/token", auto_error=False)


async def _authenticate_via_api_key(raw_key: str) -> Dict[str, Any]:
    """
    Validates an API key by hashing it and looking up the hash in DynamoDB.
    WHY: O(1) hash-based lookup is fast and avoids storing the raw key.
    The key is hashed with SHA-256 — same algorithm used at creation time.

    Args:
        raw_key (str): The raw API key from the X-API-Key header.

    Returns:
        Dict: User context with user_id and company_id.

    Raises:
        AuthenticationException: If the key is invalid, inactive, or not found.
    """
    from services.dynamo_service import get_dynamo_service

    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    db = get_dynamo_service()
    key_record = db.get_api_key_by_hash(key_hash)

    if not key_record:
        raise AuthenticationException("Invalid API key")

    if not key_record.get("is_active", False):
        raise AuthenticationException("API key has been revoked")

    # WHY: Fire-and-forget usage tracking — we don't want to block the
    # actual API response waiting for the DynamoDB update to complete.
    # If the update fails, it's logged but the request still succeeds.
    try:
        loop = asyncio.get_event_loop()
        loop.run_in_executor(None, db.update_api_key_usage, key_hash)
    except Exception:
        logger.warning(
            f"Failed to schedule API key usage update for key_id={key_record.get('key_id')}"
        )

    return {
        "user_id": str(key_record["user_id"]),
        "company_id": str(key_record["company_id"]),
    }


async def get_current_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
) -> Dict[str, Any]:
    """
    Validates authentication via API key or JWT token and returns user context.
    WHY: Supporting both auth methods allows the same protected endpoints to serve
    both browser sessions (JWT) and programmatic clients (API key) without
    requiring separate endpoint sets.

    Priority:
      1. X-API-Key header (checked first — programmatic clients)
      2. Authorization: Bearer <JWT> (fallback — browser sessions)

    Args:
        request (Request): The incoming request (for X-API-Key header access).
        token (Optional[str]): JWT token injected from Authorization header.

    Returns:
        Dict: User context containing user_id and company_id.

    Raises:
        AuthenticationException: If neither auth method provides valid credentials.
    """
    # Check for API key first
    api_key = request.headers.get("X-API-Key")
    if api_key:
        return await _authenticate_via_api_key(api_key)

    # Fall back to JWT Bearer token
    return _authenticate_via_jwt(token)


def _authenticate_via_jwt(token: Optional[str]) -> Dict[str, Any]:
    if not token:
        raise AuthenticationException("Not authenticated")

    payload = decode_access_token(token)
    user_id = payload.get("sub")
    company_id = payload.get("company_id")

    if user_id is None or company_id is None:
        raise AuthenticationException("Invalid token payload structure")

    return {"user_id": str(user_id), "company_id": str(company_id)}


async def get_session_user(
    request: Request,
    token: Optional[str] = Depends(oauth2_scheme),
) -> Dict[str, Any]:
    """
    Like get_current_user, but only accepts a browser session (JWT).
    WHY: Used for credential management. If API keys could create, rotate or delete
    API keys, one leaked key could mint replacements and revoke the owner's keys,
    keeping access after the leak is noticed.

    Raises:
        AuthorizationException: If the request carries an X-API-Key header.
        AuthenticationException: If there is no valid JWT.
    """
    if request.headers.get("X-API-Key"):
        raise AuthorizationException(
            "API keys cannot manage API keys; sign in to the dashboard instead"
        )
    return _authenticate_via_jwt(token)
