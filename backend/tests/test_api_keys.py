"""
Tests for the API key management feature:
- Schema validation (CreateApiKeyRequest, ApiKeyResponse, etc.)
- DynamoDB service methods (save, get, list, delete, usage update)
- Router endpoint logic (create, list, regenerate, revoke)
- Key generation and hashing utilities
"""

import pytest
import hashlib
from unittest.mock import patch, MagicMock
from pydantic import ValidationError
from botocore.exceptions import ClientError

from models.schemas import (
    CreateApiKeyRequest,
    CreateApiKeyResponse,
    ApiKeyResponse,
    ApiKeyListResponse,
)
from exceptions import DatabaseException, ResourceNotFoundException


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
        from routers.api_keys import _generate_raw_key

        key = _generate_raw_key()
        assert key.startswith("lw_")
        # lw_ (3 chars) + 48 hex chars = 51 total
        assert len(key) == 51

    def test_generate_raw_key_unique(self):
        from routers.api_keys import _generate_raw_key

        keys = {_generate_raw_key() for _ in range(100)}
        assert len(keys) == 100  # All unique

    def test_hash_key_deterministic(self):
        from routers.api_keys import _hash_key

        raw = "lw_test12345678901234567890123456789012345678901234"
        h1 = _hash_key(raw)
        h2 = _hash_key(raw)
        assert h1 == h2
        assert len(h1) == 64  # SHA-256 hex digest

    def test_hash_key_matches_python_hashlib(self):
        from routers.api_keys import _hash_key

        raw = "lw_somekey"
        expected = hashlib.sha256(raw.encode()).hexdigest()
        assert _hash_key(raw) == expected

    def test_build_key_record_structure(self):
        from routers.api_keys import _build_key_record

        raw = "lw_abc123def456abc123def456abc123def456abc123def456"
        record = _build_key_record(raw, "Test Key", "uid-1", "cid-1")

        assert record["key_hash"] == hashlib.sha256(raw.encode()).hexdigest()
        assert record["company_id"] == "cid-1"
        assert record["user_id"] == "uid-1"
        assert record["name"] == "Test Key"
        assert record["prefix"] == "lw_abc123d..."
        assert record["request_count"] == 0
        assert record["is_active"] is True
        assert record["last_used_at"] is None
        assert "key_id" in record
        assert "created_at" in record


# ── DynamoDB Service Method Tests ─────────────────────────────────────────


class TestDynamoServiceApiKeys:
    def test_save_api_key_success(self):
        from services.dynamo_service import DynamoDBService

        svc = MagicMock(spec=DynamoDBService)
        svc.api_keys_table = MagicMock()
        svc.api_keys_table.put_item = MagicMock()

        key_data = {"key_hash": "abc", "key_id": "kid-1"}
        DynamoDBService.save_api_key(svc, key_data)
        svc.api_keys_table.put_item.assert_called_once_with(Item=key_data)

    def test_save_api_key_failure_raises_database(self):
        from services.dynamo_service import DynamoDBService

        svc = MagicMock(spec=DynamoDBService)
        svc.api_keys_table = MagicMock()
        error_response = {"Error": {"Code": "InternalServerError", "Message": "fail"}}
        svc.api_keys_table.put_item.side_effect = ClientError(error_response, "PutItem")

        with pytest.raises(DatabaseException, match="Failed to save API key"):
            DynamoDBService.save_api_key(svc, {"key_hash": "abc"})

    def test_get_api_key_by_hash_found(self):
        from services.dynamo_service import DynamoDBService

        svc = MagicMock(spec=DynamoDBService)
        svc.api_keys_table = MagicMock()
        svc.api_keys_table.get_item.return_value = {
            "Item": {"key_hash": "abc", "company_id": "c1"}
        }

        result = DynamoDBService.get_api_key_by_hash(svc, "abc")
        assert result == {"key_hash": "abc", "company_id": "c1"}

    def test_get_api_key_by_hash_not_found(self):
        from services.dynamo_service import DynamoDBService

        svc = MagicMock(spec=DynamoDBService)
        svc.api_keys_table = MagicMock()
        svc.api_keys_table.get_item.return_value = {}

        result = DynamoDBService.get_api_key_by_hash(svc, "nonexistent")
        assert result is None

    def test_get_api_keys_by_company(self):
        from services.dynamo_service import DynamoDBService

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
        from services.dynamo_service import DynamoDBService

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
        from services.dynamo_service import DynamoDBService

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
        from services.dynamo_service import DynamoDBService

        svc = MagicMock(spec=DynamoDBService)
        svc.api_keys_table = MagicMock()
        svc.api_keys_table.delete_item = MagicMock()

        DynamoDBService.delete_api_key(svc, "hash123")
        svc.api_keys_table.delete_item.assert_called_once_with(
            Key={"key_hash": "hash123"}
        )

    def test_update_api_key_usage(self):
        from services.dynamo_service import DynamoDBService

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
        from services.dynamo_service import DynamoDBService

        svc = MagicMock(spec=DynamoDBService)
        svc.api_keys_table = MagicMock()
        error_response = {"Error": {"Code": "InternalServerError", "Message": "fail"}}
        svc.api_keys_table.update_item.side_effect = ClientError(
            error_response, "UpdateItem"
        )

        # Should not raise — the method swallows the error
        DynamoDBService.update_api_key_usage(svc, "hash123")


# ── Router Endpoint Tests ─────────────────────────────────────────────────


class TestApiKeysRouter:
    """Tests for the API keys router endpoints using FastAPI TestClient."""

    def _get_test_client(self):
        """Create a TestClient with mocked dependencies."""
        from fastapi.testclient import TestClient
        from main import app
        from auth.dependencies import get_current_user

        async def mock_user():
            return {"user_id": "test-user", "company_id": "test-company"}

        app.dependency_overrides[get_current_user] = mock_user
        client = TestClient(app)
        return client, app

    def _cleanup(self, app):
        app.dependency_overrides.clear()

    def test_create_api_key(self):
        client, app = self._get_test_client()
        try:
            with patch("routers.api_keys.get_dynamo_service") as mock_get_db:
                mock_db = MagicMock()
                mock_db.save_api_key = MagicMock()
                mock_get_db.return_value = mock_db

                response = client.post(
                    "/api-keys",
                    json={"name": "Production Key"},
                )
                assert response.status_code == 201
                data = response.json()
                assert data["name"] == "Production Key"
                assert data["raw_key"].startswith("lw_")
                assert len(data["raw_key"]) == 51
                assert "key_id" in data
                assert "prefix" in data
                assert "created_at" in data
                mock_db.save_api_key.assert_called_once()
        finally:
            self._cleanup(app)

    def test_create_api_key_empty_name_rejected(self):
        client, app = self._get_test_client()
        try:
            response = client.post("/api-keys", json={"name": ""})
            assert response.status_code == 422  # Validation error
        finally:
            self._cleanup(app)

    def test_list_api_keys(self):
        client, app = self._get_test_client()
        try:
            with patch("routers.api_keys.get_dynamo_service") as mock_get_db:
                mock_db = MagicMock()
                mock_db.get_api_keys_by_company.return_value = [
                    {
                        "key_id": "kid-1",
                        "name": "Key One",
                        "prefix": "lw_abc1...",
                        "created_at": "2026-01-01T00:00:00+00:00",
                        "last_used_at": None,
                        "request_count": 0,
                        "is_active": True,
                    },
                    {
                        "key_id": "kid-2",
                        "name": "Key Two",
                        "prefix": "lw_def2...",
                        "created_at": "2026-02-01T00:00:00+00:00",
                        "last_used_at": "2026-03-01T00:00:00+00:00",
                        "request_count": 15,
                        "is_active": True,
                    },
                ]
                mock_get_db.return_value = mock_db

                response = client.get("/api-keys")
                assert response.status_code == 200
                data = response.json()
                assert len(data["keys"]) == 2
                assert data["keys"][0]["name"] == "Key One"
                assert data["keys"][1]["request_count"] == 15
                # Ensure raw_key is NOT in the list response
                for key in data["keys"]:
                    assert "raw_key" not in key
        finally:
            self._cleanup(app)

    def test_regenerate_api_key(self):
        client, app = self._get_test_client()
        try:
            with patch("routers.api_keys.get_dynamo_service") as mock_get_db:
                mock_db = MagicMock()
                mock_db.get_api_key_by_id.return_value = {
                    "key_hash": "old_hash",
                    "key_id": "kid-1",
                    "name": "My Key",
                    "company_id": "test-company",
                }
                mock_db.delete_api_key = MagicMock()
                mock_db.save_api_key = MagicMock()
                mock_get_db.return_value = mock_db

                response = client.post("/api-keys/kid-1/regenerate")
                assert response.status_code == 200
                data = response.json()
                assert data["name"] == "My Key"
                assert data["raw_key"].startswith("lw_")
                assert data["key_id"] != "kid-1"  # New key_id
                mock_db.delete_api_key.assert_called_once_with("old_hash")
                mock_db.save_api_key.assert_called_once()
        finally:
            self._cleanup(app)

    def test_regenerate_api_key_not_found(self):
        client, app = self._get_test_client()
        try:
            with patch("routers.api_keys.get_dynamo_service") as mock_get_db:
                mock_db = MagicMock()
                mock_db.get_api_key_by_id.return_value = None
                mock_get_db.return_value = mock_db

                response = client.post("/api-keys/nonexistent/regenerate")
                assert response.status_code == 404
        finally:
            self._cleanup(app)

    def test_revoke_api_key(self):
        client, app = self._get_test_client()
        try:
            with patch("routers.api_keys.get_dynamo_service") as mock_get_db:
                mock_db = MagicMock()
                mock_db.get_api_key_by_id.return_value = {
                    "key_hash": "some_hash",
                    "key_id": "kid-1",
                    "company_id": "test-company",
                }
                mock_db.delete_api_key = MagicMock()
                mock_get_db.return_value = mock_db

                response = client.delete("/api-keys/kid-1")
                assert response.status_code == 204
                mock_db.delete_api_key.assert_called_once_with("some_hash")
        finally:
            self._cleanup(app)

    def test_revoke_api_key_not_found(self):
        client, app = self._get_test_client()
        try:
            with patch("routers.api_keys.get_dynamo_service") as mock_get_db:
                mock_db = MagicMock()
                mock_db.get_api_key_by_id.return_value = None
                mock_get_db.return_value = mock_db

                response = client.delete("/api-keys/nonexistent")
                assert response.status_code == 404
        finally:
            self._cleanup(app)
