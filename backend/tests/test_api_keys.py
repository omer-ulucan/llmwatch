"""
Tests for the API key management feature:
- Schema validation (CreateApiKeyRequest, ApiKeyResponse, etc.)
- DynamoDB service methods (save, get, list, delete, usage update)
- Router endpoint logic (create, list, regenerate, revoke)
- Key generation and hashing utilities
"""

import hashlib
from unittest.mock import MagicMock

import pytest
from botocore.exceptions import ClientError
from pydantic import ValidationError

from llmwatch.exceptions import DatabaseException
from llmwatch.models.schemas import (
    ApiKeyListResponse,
    ApiKeyResponse,
    CreateApiKeyRequest,
    CreateApiKeyResponse,
)

# ── Schema Validation Tests ───────────────────────────────────────────────


class TestCreateApiKeyRequest:
    def test_valid_name(self):
        req = CreateApiKeyRequest(name="Production SDK")
        assert req.name == "Production SDK"

    def test_empty_name_rejected(self):
        with pytest.raises(ValidationError):
            CreateApiKeyRequest(name="")

    def test_long_name_rejected(self):
        with pytest.raises(ValidationError):
            CreateApiKeyRequest(name="x" * 65)

    def test_extra_fields_rejected(self):
        with pytest.raises(ValidationError):
            CreateApiKeyRequest(name="test", scope="admin")  # type: ignore[call-arg]

    def test_max_length_name_accepted(self):
        req = CreateApiKeyRequest(name="x" * 64)
        assert len(req.name) == 64


class TestCreateApiKeyResponse:
    def test_valid_response(self):
        resp = CreateApiKeyResponse(
            key_id="kid-1",
            name="Test Key",
            raw_key="lw_abc123",
            prefix="lw_abc123...",
            created_at="2026-01-01T00:00:00+00:00",
        )
        assert resp.key_id == "kid-1"
        assert resp.raw_key == "lw_abc123"


class TestApiKeyResponse:
    def test_defaults(self):
        resp = ApiKeyResponse(
            key_id="kid-1",
            name="Test",
            prefix="lw_abc1...",
            created_at="2026-01-01T00:00:00+00:00",
        )
        assert resp.last_used_at is None
        assert resp.request_count == 0
        assert resp.is_active is True

    def test_with_usage(self):
        resp = ApiKeyResponse(
            key_id="kid-2",
            name="CI Key",
            prefix="lw_def2...",
            created_at="2026-01-01T00:00:00+00:00",
            last_used_at="2026-03-08T12:00:00+00:00",
            request_count=42,
            is_active=True,
        )
        assert resp.request_count == 42
        assert resp.last_used_at is not None


class TestApiKeyListResponse:
    def test_empty_list(self):
        resp = ApiKeyListResponse(keys=[])
        assert resp.keys == []

    def test_multiple_keys(self):
        keys = [
            ApiKeyResponse(
                key_id=f"kid-{i}",
                name=f"Key {i}",
                prefix=f"lw_{i}abc...",
                created_at="2026-01-01T00:00:00+00:00",
            )
            for i in range(3)
        ]
        resp = ApiKeyListResponse(keys=keys)
        assert len(resp.keys) == 3


# ── Key Generation & Hashing Tests ───────────────────────────────────────


class TestKeyGeneration:
    def test_generate_raw_key_format(self):
        from llmwatch.routers.api_keys import _generate_raw_key

        key = _generate_raw_key()
        assert key.startswith("lw_")
        # lw_ (3 chars) + 48 hex chars = 51 total
        assert len(key) == 51

    def test_generate_raw_key_unique(self):
        from llmwatch.routers.api_keys import _generate_raw_key

        keys = {_generate_raw_key() for _ in range(100)}
        assert len(keys) == 100  # All unique

    def test_hash_key_deterministic(self):
        from llmwatch.routers.api_keys import _hash_key

        raw = "lw_test12345678901234567890123456789012345678901234"
        h1 = _hash_key(raw)
        h2 = _hash_key(raw)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest

    def test_hash_key_matches_python_hashlib(self):
        from llmwatch.routers.api_keys import _hash_key

        raw = "lw_somekey"
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert _hash_key(raw) == expected

    def test_new_key_structure(self):
        from llmwatch.routers.api_keys import _new_key

        raw = "lw_abc123def456abc123def456abc123def456abc123def456"
        key = _new_key(raw, "Test Key", "uid-1")

        assert key.key_hash == hashlib.sha256(raw.encode()).hexdigest()
        assert key.user_id == "uid-1"
        assert key.name == "Test Key"
        assert key.prefix == "lw_abc123d..."


# ── DynamoDB Service Method Tests ─────────────────────────────────────────


class TestDynamoServiceApiKeys:
    def test_save_api_key_success(self):
        from llmwatch.services.dynamo_service import DynamoDBService

        svc = MagicMock(spec=DynamoDBService)
        svc.api_keys_table = MagicMock()
        svc.api_keys_table.put_item = MagicMock()

        key_data = {"key_hash": "abc", "key_id": "kid-1"}
        DynamoDBService.save_api_key(svc, key_data)
        svc.api_keys_table.put_item.assert_called_once_with(Item=key_data)

    def test_save_api_key_failure_raises_database(self):
        from llmwatch.services.dynamo_service import DynamoDBService

        svc = MagicMock(spec=DynamoDBService)
        svc.api_keys_table = MagicMock()
        error_response = {"Error": {"Code": "InternalServerError", "Message": "fail"}}
        svc.api_keys_table.put_item.side_effect = ClientError(error_response, "PutItem")

        with pytest.raises(DatabaseException, match="Failed to save API key"):
            DynamoDBService.save_api_key(svc, {"key_hash": "abc"})

    def test_get_api_key_by_hash_found(self):
        from llmwatch.services.dynamo_service import DynamoDBService

        svc = MagicMock(spec=DynamoDBService)
        svc.api_keys_table = MagicMock()
        svc.api_keys_table.get_item.return_value = {
            "Item": {"key_hash": "abc", "company_id": "c1"}
        }

        result = DynamoDBService.get_api_key_by_hash(svc, "abc")
        assert result == {"key_hash": "abc", "company_id": "c1"}

    def test_get_api_key_by_hash_not_found(self):
        from llmwatch.services.dynamo_service import DynamoDBService

        svc = MagicMock(spec=DynamoDBService)
        svc.api_keys_table = MagicMock()
        svc.api_keys_table.get_item.return_value = {}

        result = DynamoDBService.get_api_key_by_hash(svc, "nonexistent")
        assert result is None

    def test_get_api_keys_by_company(self):
        from llmwatch.services.dynamo_service import DynamoDBService

        svc = MagicMock(spec=DynamoDBService)
        svc.api_keys_table = MagicMock()
        svc.api_keys_table.query.return_value = {
            "Items": [
                {"key_id": "k1", "company_id": "c1"},
                {"key_id": "k2", "company_id": "c1"},
            ]
        }

        result = DynamoDBService.get_api_keys_by_company(svc, "c1")
        assert len(result) == 2

    def test_get_api_key_by_id_found_and_owned(self):
        from llmwatch.services.dynamo_service import DynamoDBService

        svc = MagicMock(spec=DynamoDBService)
        svc.api_keys_table = MagicMock()
        svc.api_keys_table.query.return_value = {
            "Items": [{"key_id": "kid-1", "company_id": "c1", "key_hash": "h1"}]
        }

        result = DynamoDBService.get_api_key_by_id(svc, "c1", "kid-1")
        assert result is not None
        assert result["key_id"] == "kid-1"

    def test_get_api_key_by_id_cross_tenant_rejected(self):
        """Key found but owned by different company — should return None."""
        from llmwatch.services.dynamo_service import DynamoDBService

        svc = MagicMock(spec=DynamoDBService)
        svc.api_keys_table = MagicMock()
        svc.api_keys_table.query.return_value = {
            "Items": [
                {"key_id": "kid-1", "company_id": "other-company", "key_hash": "h1"}
            ]
        }

        result = DynamoDBService.get_api_key_by_id(svc, "my-company", "kid-1")
        assert result is None

    def test_delete_api_key_success(self):
        from llmwatch.services.dynamo_service import DynamoDBService

        svc = MagicMock(spec=DynamoDBService)
        svc.api_keys_table = MagicMock()
        svc.api_keys_table.delete_item = MagicMock()

        DynamoDBService.delete_api_key(svc, "hash123")
        svc.api_keys_table.delete_item.assert_called_once_with(
            Key={"key_hash": "hash123"}
        )

    def test_update_api_key_usage(self):
        from llmwatch.services.dynamo_service import DynamoDBService

        svc = MagicMock(spec=DynamoDBService)
        svc.api_keys_table = MagicMock()
        svc.api_keys_table.update_item = MagicMock()

        DynamoDBService.update_api_key_usage(svc, "hash123")
        svc.api_keys_table.update_item.assert_called_once()

        call_kwargs = svc.api_keys_table.update_item.call_args
        assert "request_count" in str(call_kwargs)
        assert "last_used_at" in str(call_kwargs)

    def test_update_api_key_usage_failure_does_not_raise(self):
        """Usage tracking failure should be silent (logged, not re-raised)."""
        from llmwatch.services.dynamo_service import DynamoDBService

        svc = MagicMock(spec=DynamoDBService)
        svc.api_keys_table = MagicMock()
        error_response = {"Error": {"Code": "InternalServerError", "Message": "fail"}}
        svc.api_keys_table.update_item.side_effect = ClientError(
            error_response, "UpdateItem"
        )

        # Should not raise — the method swallows the error
        DynamoDBService.update_api_key_usage(svc, "hash123")


# ── Router Endpoint Tests (SQL) ───────────────────────────────────────────


class TestApiKeysRouter:
    """The /api-keys endpoints against the real database layer."""

    async def test_create_api_key(self, client, make_account):
        owner = await make_account()
        response = await client.post(
            "/api-keys", json={"name": "Production Key"}, headers=owner.headers
        )
        assert response.status_code == 201
        data = response.json()
        assert data["name"] == "Production Key"
        assert data["raw_key"].startswith("lw_")
        assert len(data["raw_key"]) == 51
        assert data["prefix"] == data["raw_key"][:10] + "..."

    async def test_raw_key_is_not_stored(self, client, make_account, db_session):
        from sqlalchemy import select

        from llmwatch.db.models import ApiKey

        owner = await make_account()
        raw = (
            await client.post("/api-keys", json={"name": "k"}, headers=owner.headers)
        ).json()["raw_key"]

        stored = (await db_session.execute(select(ApiKey))).scalar_one()
        assert stored.key_hash == hashlib.sha256(raw.encode()).hexdigest()
        assert raw not in {stored.key_hash, stored.prefix, stored.name}

    async def test_create_api_key_empty_name_rejected(self, client, make_account):
        owner = await make_account()
        response = await client.post(
            "/api-keys", json={"name": ""}, headers=owner.headers
        )
        assert response.status_code == 422

    async def test_list_api_keys(self, client, make_account):
        owner = await make_account()
        for name in ("one", "two"):
            await client.post("/api-keys", json={"name": name}, headers=owner.headers)

        response = await client.get("/api-keys", headers=owner.headers)
        assert response.status_code == 200
        keys = response.json()["keys"]
        assert sorted(k["name"] for k in keys) == ["one", "two"]
        for k in keys:
            assert "raw_key" not in k
            assert k["request_count"] == 0
            assert k["last_used_at"] is None

    async def test_list_only_shows_own_workspace(self, client, make_account):
        alice = await make_account(workspace="A")
        bob = await make_account(workspace="B")
        await client.post("/api-keys", json={"name": "alice"}, headers=alice.headers)

        response = await client.get("/api-keys", headers=bob.headers)
        assert response.json()["keys"] == []

    async def test_regenerate_api_key(self, client, make_account):
        owner = await make_account()
        old = (
            await client.post("/api-keys", json={"name": "CI"}, headers=owner.headers)
        ).json()

        response = await client.post(
            f"/api-keys/{old['key_id']}/regenerate", headers=owner.headers
        )
        assert response.status_code == 200
        new = response.json()
        assert new["name"] == "CI"
        assert new["raw_key"] != old["raw_key"]
        assert new["key_id"] != old["key_id"]

        # Old key no longer authenticates; the new one does.
        assert (
            await client.get("/auth/me", headers={"X-API-Key": old["raw_key"]})
        ).status_code == 401
        assert (
            await client.get("/auth/me", headers={"X-API-Key": new["raw_key"]})
        ).status_code == 200

    async def test_regenerate_api_key_not_found(self, client, make_account):
        owner = await make_account()
        response = await client.post(
            "/api-keys/nonexistent-id/regenerate", headers=owner.headers
        )
        assert response.status_code == 404

    async def test_revoke_api_key(self, client, make_account):
        owner = await make_account()
        created = (
            await client.post("/api-keys", json={"name": "k"}, headers=owner.headers)
        ).json()

        response = await client.delete(
            f"/api-keys/{created['key_id']}", headers=owner.headers
        )
        assert response.status_code == 204
        assert (
            await client.get("/auth/me", headers={"X-API-Key": created["raw_key"]})
        ).status_code == 401

    async def test_revoke_api_key_not_found(self, client, make_account):
        owner = await make_account()
        response = await client.delete(
            "/api-keys/nonexistent-id", headers=owner.headers
        )
        assert response.status_code == 404

    async def test_cannot_touch_another_workspaces_key(self, client, make_account):
        alice = await make_account(workspace="A")
        bob = await make_account(workspace="B")
        key = (
            await client.post("/api-keys", json={"name": "a"}, headers=alice.headers)
        ).json()

        for method, path in [
            ("post", f"/api-keys/{key['key_id']}/regenerate"),
            ("delete", f"/api-keys/{key['key_id']}"),
        ]:
            resp = await client.request(method, path, headers=bob.headers)
            assert resp.status_code == 404
        # Alice's key still works.
        assert (
            await client.get("/auth/me", headers={"X-API-Key": key["raw_key"]})
        ).status_code == 200
