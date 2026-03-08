"""
Tests for the auth dependency (get_current_user) in auth/dependencies.py.
"""

import pytest
from unittest.mock import patch

from auth.dependencies import get_current_user
from auth.jwt_handler import create_access_token
from exceptions import AuthenticationException


class TestGetCurrentUser:
    @pytest.mark.asyncio
    async def test_valid_token_returns_user_dict(self):
        token = create_access_token(data={"sub": "user-1", "company_id": "comp-1"})
        result = await get_current_user(token=token)
        assert result == {"user_id": "user-1", "company_id": "comp-1"}

    @pytest.mark.asyncio
    async def test_missing_sub_raises(self):
        token = create_access_token(data={"company_id": "comp-1"})
        with pytest.raises(AuthenticationException) as exc_info:
            await get_current_user(token=token)
        assert (
            "payload" in exc_info.value.message.lower()
            or "Invalid" in exc_info.value.message
        )

    @pytest.mark.asyncio
    async def test_missing_company_id_raises(self):
        token = create_access_token(data={"sub": "user-1"})
        with pytest.raises(AuthenticationException) as exc_info:
            await get_current_user(token=token)
        assert (
            "payload" in exc_info.value.message.lower()
            or "Invalid" in exc_info.value.message
        )

    @pytest.mark.asyncio
    async def test_invalid_token_raises(self):
        with pytest.raises(AuthenticationException):
            await get_current_user(token="garbage-token")

    @pytest.mark.asyncio
    async def test_empty_token_raises(self):
        with pytest.raises(AuthenticationException):
            await get_current_user(token="")
