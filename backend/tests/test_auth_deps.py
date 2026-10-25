"""
Tests for the auth dependency (get_current_user) in auth/dependencies.py.
WHY: Covers both JWT and API key authentication paths against the real database.
"""

from datetime import timedelta

import pytest
from sqlalchemy import select

from llmwatch.auth.jwt_handler import create_access_token
from llmwatch.db.models import ApiKey, User


async def _api_key(client, account) -> dict:
    resp = await client.post("/api-keys", json={"name": "k"}, headers=account.headers)
    assert resp.status_code == 201
    return resp.json()


class TestJWT:
    async def test_valid_token_returns_user_context(self, client, make_account):
        acct = await make_account(email="alice@example.com", workspace="Acme")
        resp = await client.get("/auth/me", headers=acct.headers)

        assert resp.status_code == 200
        body = resp.json()
        assert body["user"] == {
            "id": acct.user_id,
            "email": "alice@example.com",
            "role": "owner",
        }
        assert body["workspace"]["id"] == acct.workspace_id
        assert body["workspace"]["name"] == "Acme"
        assert body["auth_method"] == "jwt"

    async def test_missing_token_is_401(self, client):
        resp = await client.get("/auth/me")
        assert resp.status_code == 401
        assert resp.json()["code"] == "AUTHENTICATION_FAILED"

    async def test_garbage_token_is_401(self, client):
        resp = await client.get("/auth/me", headers={"Authorization": "Bearer junk"})
        assert resp.status_code == 401

    async def test_expired_token_is_401(self, client, make_account):
        acct = await make_account()
        token = create_access_token(
            {"sub": acct.user_id}, expires_delta=timedelta(seconds=-1)
        )
        resp = await client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.status_code == 401

    async def test_token_for_deleted_user_is_401(
        self, client, make_account, db_session
    ):
        acct = await make_account()
        user = await db_session.get(User, acct.user_id)
        await db_session.delete(user)
        await db_session.commit()

        resp = await client.get("/auth/me", headers=acct.headers)
        assert resp.status_code == 401

    async def test_token_for_deactivated_user_is_401(
        self, client, make_account, db_session
    ):
        acct = await make_account()
        user = await db_session.get(User, acct.user_id)
        user.is_active = False
        await db_session.commit()

        resp = await client.get("/auth/me", headers=acct.headers)
        assert resp.status_code == 401
        assert "disabled" in resp.json()["error"].lower()

    async def test_workspace_comes_from_db_not_token(self, client, make_account):
        """A forged workspace claim in a validly signed token is ignored."""
        alice = await make_account(workspace="A")
        bob = await make_account(workspace="B")
        token = create_access_token(
            {"sub": alice.user_id, "workspace_id": bob.workspace_id}
        )
        resp = await client.get(
            "/auth/me", headers={"Authorization": f"Bearer {token}"}
        )
        assert resp.json()["workspace"]["id"] == alice.workspace_id


class TestApiKey:
    async def test_valid_api_key_returns_user_context(self, client, make_account):
        acct = await make_account()
        key = await _api_key(client, acct)

        resp = await client.get("/auth/me", headers={"X-API-Key": key["raw_key"]})
        assert resp.status_code == 200
        body = resp.json()
        assert body["auth_method"] == "api_key"
        assert body["user"]["id"] == acct.user_id
        assert body["workspace"]["id"] == acct.workspace_id

    async def test_unknown_api_key_is_401(self, client):
        resp = await client.get("/auth/me", headers={"X-API-Key": "lw_" + "0" * 48})
        assert resp.status_code == 401
        assert resp.json()["error"] == "Invalid API key"

    async def test_inactive_api_key_is_401(self, client, make_account, db_session):
        acct = await make_account()
        key = await _api_key(client, acct)
        row = (await db_session.execute(select(ApiKey))).scalar_one()
        row.is_active = False
        await db_session.commit()

        resp = await client.get("/auth/me", headers={"X-API-Key": key["raw_key"]})
        assert resp.status_code == 401
        assert "revoked" in resp.json()["error"]

    async def test_api_key_usage_is_tracked(self, client, make_account, db_session):
        acct = await make_account()
        key = await _api_key(client, acct)
        for _ in range(3):
            await client.get("/auth/me", headers={"X-API-Key": key["raw_key"]})

        row = (await db_session.execute(select(ApiKey))).scalar_one()
        await db_session.refresh(row)
        assert row.request_count == 3
        assert row.last_used_at is not None

    async def test_api_key_of_deactivated_user_is_401(
        self, client, make_account, db_session
    ):
        acct = await make_account()
        key = await _api_key(client, acct)
        user = await db_session.get(User, acct.user_id)
        user.is_active = False
        await db_session.commit()

        resp = await client.get("/auth/me", headers={"X-API-Key": key["raw_key"]})
        assert resp.status_code == 401

    async def test_api_key_takes_priority_over_jwt(self, client, make_account):
        alice = await make_account(workspace="A")
        bob = await make_account(workspace="B")
        key = await _api_key(client, bob)

        resp = await client.get(
            "/auth/me", headers={**alice.headers, "X-API-Key": key["raw_key"]}
        )
        assert resp.json()["workspace"]["id"] == bob.workspace_id

    @pytest.mark.parametrize("header", ["x-api-key", "X-API-KEY"])
    async def test_header_name_is_case_insensitive(self, client, make_account, header):
        acct = await make_account()
        key = await _api_key(client, acct)
        resp = await client.get("/auth/me", headers={header: key["raw_key"]})
        assert resp.status_code == 200
