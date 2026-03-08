"""
Tests for the auth dependency (get_current_user) in auth/dependencies.py.
WHY: Covers both JWT and API key authentication paths.
"""

import pytest
from unittest.mock import patch, MagicMock, AsyncMock

from auth.dependencies import get_current_user
from auth.jwt_handler import create_access_token
from exceptions import AuthenticationException


def _make_request(api_key: str = None) -> MagicMock:
    """Create a mock FastAPI Request with optional X-API-Key header."""
    request = MagicMock()
    headers = {}
    if api_key:
        headers["X-API-Key"] = api_key
    request.headers = headers
    return request


class TestGetCurrentUserJWT:
    """Tests for JWT Bearer token authentication path."""

    @pytest.mark.asyncio
    async def test_valid_token_returns_user_dict(self):
        token = create_access_token(data={"sub": "user-1", "company_id": "comp-1"})
        request = _make_request()
        result = await get_current_user(request=request, token=token)
        assert result == {"user_id": "user-1", "company_id": "comp-1"}

    @pytest.mark.asyncio
    async def test_missing_sub_raises(self):
        token = create_access_token(data={"company_id": "comp-1"})
        request = _make_request()
        with pytest.raises(AuthenticationException) as exc_info:
            await get_current_user(request=request, token=token)
        assert (
            "payload" in exc_info.value.message.lower()
            or "Invalid" in exc_info.value.message
        )

    @pytest.mark.asyncio
    async def test_missing_company_id_raises(self):
        token = create_access_token(data={"sub": "user-1"})
        request = _make_request()
        with pytest.raises(AuthenticationException) as exc_info:
            await get_current_user(request=request, token=token)
        assert (
            "payload" in exc_info.value.message.lower()
            or "Invalid" in exc_info.value.message
        )

    @pytest.mark.asyncio
    async def test_invalid_token_raises(self):
        request = _make_request()
        with pytest.raises(AuthenticationException):
            await get_current_user(request=request, token="garbage-token")

    @pytest.mark.asyncio
    async def test_empty_token_raises(self):
        request = _make_request()
        with pytest.raises(AuthenticationException):
            await get_current_user(request=request, token="")

    @pytest.mark.asyncio
    async def test_no_token_no_api_key_raises(self):
        """Neither auth method provided should raise."""
        request = _make_request()
        with pytest.raises(AuthenticationException, match="Not authenticated"):
            await get_current_user(request=request, token=None)


class TestGetCurrentUserApiKey:
    """Tests for X-API-Key header authentication path."""

    @pytest.mark.asyncio
    async def test_valid_api_key_returns_user_dict(self):
        """A valid API key should return user context from DynamoDB."""
        import hashlib

        raw_key = "lw_abc123def456abc123def456abc123def456abc123def456"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        mock_record = {
            "key_hash": key_hash,
            "key_id": "kid-1",
            "user_id": "user-api",
            "company_id": "comp-api",
            "is_active": True,
        }

        request = _make_request(api_key=raw_key)

        with patch("services.dynamo_service.get_dynamo_service") as mock_get_db:
            mock_db = MagicMock()
            mock_db.get_api_key_by_hash.return_value = mock_record
            mock_db.update_api_key_usage = MagicMock()
            mock_get_db.return_value = mock_db

            result = await get_current_user(request=request, token=None)
            assert result == {"user_id": "user-api", "company_id": "comp-api"}
            mock_db.get_api_key_by_hash.assert_called_once_with(key_hash)

    @pytest.mark.asyncio
    async def test_invalid_api_key_raises(self):
        """An API key not found in DynamoDB should raise AuthenticationException."""
        request = _make_request(
            api_key="lw_nonexistentkey12345678901234567890123456789012"
        )

        with patch("services.dynamo_service.get_dynamo_service") as mock_get_db:
            mock_db = MagicMock()
            mock_db.get_api_key_by_hash.return_value = None
            mock_get_db.return_value = mock_db

            with pytest.raises(AuthenticationException, match="Invalid API key"):
                await get_current_user(request=request, token=None)

    @pytest.mark.asyncio
    async def test_inactive_api_key_raises(self):
        """A revoked (is_active=False) key should raise AuthenticationException."""
        import hashlib

        raw_key = "lw_revokedkey123456789012345678901234567890123456"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        mock_record = {
            "key_hash": key_hash,
            "key_id": "kid-2",
            "user_id": "user-x",
            "company_id": "comp-x",
            "is_active": False,
        }

        request = _make_request(api_key=raw_key)

        with patch("services.dynamo_service.get_dynamo_service") as mock_get_db:
            mock_db = MagicMock()
            mock_db.get_api_key_by_hash.return_value = mock_record
            mock_get_db.return_value = mock_db

            with pytest.raises(AuthenticationException, match="revoked"):
                await get_current_user(request=request, token=None)

    @pytest.mark.asyncio
    async def test_api_key_takes_priority_over_jwt(self):
        """When both X-API-Key and Bearer token are provided, API key wins."""
        import hashlib

        raw_key = "lw_prioritytest1234567890123456789012345678901234"
        key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

        mock_record = {
            "key_hash": key_hash,
            "key_id": "kid-3",
            "user_id": "api-user",
            "company_id": "api-comp",
            "is_active": True,
        }

        jwt_token = create_access_token(
            data={"sub": "jwt-user", "company_id": "jwt-comp"}
        )
        request = _make_request(api_key=raw_key)

        with patch("services.dynamo_service.get_dynamo_service") as mock_get_db:
            mock_db = MagicMock()
            mock_db.get_api_key_by_hash.return_value = mock_record
            mock_db.update_api_key_usage = MagicMock()
            mock_get_db.return_value = mock_db

            result = await get_current_user(request=request, token=jwt_token)
            # API key should win over JWT
            assert result == {"user_id": "api-user", "company_id": "api-comp"}
