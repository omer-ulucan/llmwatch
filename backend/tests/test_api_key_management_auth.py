"""
Regression tests: API keys must not be able to manage API keys.

WHY: Key management accepted the same auth as every other endpoint, so a leaked
API key (e.g. from a CI log) could mint new keys, rotate or delete the owner's keys
and lock them out while keeping access. Managing keys now requires a browser
session (JWT); API keys get 403 here and still work everywhere else.
"""

from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from auth.jwt_handler import create_access_token
from rate_limit import limiter

RAW_KEY = "lw_" + "a" * 48
KEY_RECORD = {
    "key_hash": "h",
    "key_id": "key-1",
    "company_id": "company-1",
    "user_id": "user-1",
    "name": "CI",
    "prefix": "lw_aaaaaaa...",
    "created_at": "2026-01-01T00:00:00+00:00",
    "is_active": True,
    "request_count": 0,
}


@pytest.fixture
def client():
    from main import app

    limiter.reset()
    db = MagicMock()
    db.get_api_key_by_hash.return_value = KEY_RECORD
    db.get_api_key_by_id.return_value = KEY_RECORD
    db.get_api_keys_by_company.return_value = [KEY_RECORD]
    with (
        patch("services.dynamo_service.get_dynamo_service", return_value=db),
        patch("routers.api_keys.get_dynamo_service", return_value=db),
    ):
        yield TestClient(app), db
    limiter.reset()


def _jwt_headers() -> dict[str, str]:
    token = create_access_token({"sub": "user-1", "company_id": "company-1"})
    return {"Authorization": f"Bearer {token}"}


API_KEY_HEADERS = {"X-API-Key": RAW_KEY}

MANAGEMENT_CALLS = [
    ("post", "/api-keys", {"name": "minted-by-leaked-key"}),
    ("get", "/api-keys", None),
    ("post", "/api-keys/key-1/regenerate", None),
    ("delete", "/api-keys/key-1", None),
]


@pytest.mark.parametrize("method,path,body", MANAGEMENT_CALLS)
def test_api_key_cannot_manage_api_keys(client, method, path, body):
    http, db = client
    resp = http.request(method, path, json=body, headers=API_KEY_HEADERS)

    assert resp.status_code == 403
    assert resp.json()["code"] == "AUTHORIZATION_FAILED"
    db.save_api_key.assert_not_called()
    db.delete_api_key.assert_not_called()


@pytest.mark.parametrize("method,path,body", MANAGEMENT_CALLS)
def test_api_key_alongside_jwt_is_still_refused(client, method, path, body):
    http, db = client
    headers = {**_jwt_headers(), **API_KEY_HEADERS}
    resp = http.request(method, path, json=body, headers=headers)

    assert resp.status_code == 403
    db.save_api_key.assert_not_called()
    db.delete_api_key.assert_not_called()


def test_jwt_session_can_create_api_key(client):
    http, db = client
    resp = http.post("/api-keys", json={"name": "New"}, headers=_jwt_headers())

    assert resp.status_code == 201
    db.save_api_key.assert_called_once()


def test_jwt_session_can_list_rotate_and_revoke(client):
    http, db = client
    assert http.get("/api-keys", headers=_jwt_headers()).status_code == 200
    assert (
        http.post("/api-keys/key-1/regenerate", headers=_jwt_headers()).status_code
        == 200
    )
    assert http.delete("/api-keys/key-1", headers=_jwt_headers()).status_code == 204


def test_unauthenticated_key_management_is_401(client):
    http, _ = client
    assert http.get("/api-keys").status_code == 401


def test_api_keys_still_work_on_other_endpoints(client):
    http, _ = client
    resp = http.get("/agent/tools", headers=API_KEY_HEADERS)
    assert resp.status_code == 200
