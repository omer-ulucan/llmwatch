"""
Regression tests: API keys must not be able to manage API keys.

WHY: Key management accepted the same auth as every other endpoint, so a leaked
API key (e.g. from a CI log) could mint new keys, rotate or delete the owner's keys
and lock them out while keeping access. Managing keys now requires a browser
session (JWT); API keys get 403 here and still work everywhere else.
"""

import pytest
from sqlalchemy import func, select

from llmwatch.db.models import ApiKey


@pytest.fixture
async def owner_with_key(client, make_account):
    owner = await make_account()
    resp = await client.post("/api-keys", json={"name": "CI"}, headers=owner.headers)
    assert resp.status_code == 201
    return owner, resp.json()


def _management_calls(key_id: str):
    return [
        ("post", "/api-keys", {"name": "minted-by-leaked-key"}),
        ("get", "/api-keys", None),
        ("post", f"/api-keys/{key_id}/regenerate", None),
        ("delete", f"/api-keys/{key_id}", None),
    ]


async def _key_count(db_session) -> int:
    return (
        await db_session.execute(select(func.count()).select_from(ApiKey))
    ).scalar_one()


async def test_api_key_cannot_manage_api_keys(client, owner_with_key, db_session):
    _, key = owner_with_key
    for method, path, body in _management_calls(key["key_id"]):
        resp = await client.request(
            method, path, json=body, headers={"X-API-Key": key["raw_key"]}
        )
        assert resp.status_code == 403, (method, path)
        assert resp.json()["code"] == "AUTHORIZATION_FAILED"
    assert await _key_count(db_session) == 1


async def test_api_key_alongside_jwt_is_still_refused(
    client, owner_with_key, db_session
):
    owner, key = owner_with_key
    headers = {**owner.headers, "X-API-Key": key["raw_key"]}
    for method, path, body in _management_calls(key["key_id"]):
        resp = await client.request(method, path, json=body, headers=headers)
        assert resp.status_code == 403, (method, path)
    assert await _key_count(db_session) == 1


async def test_jwt_session_can_manage_keys(client, owner_with_key):
    owner, key = owner_with_key
    assert (await client.get("/api-keys", headers=owner.headers)).status_code == 200
    regenerated = await client.post(
        f"/api-keys/{key['key_id']}/regenerate", headers=owner.headers
    )
    assert regenerated.status_code == 200
    new_id = regenerated.json()["key_id"]
    assert (
        await client.delete(f"/api-keys/{new_id}", headers=owner.headers)
    ).status_code == 204


async def test_unauthenticated_key_management_is_401(client):
    assert (await client.get("/api-keys")).status_code == 401


async def test_api_keys_still_work_on_other_endpoints(client, owner_with_key):
    _, key = owner_with_key
    resp = await client.get("/agent/tools", headers={"X-API-Key": key["raw_key"]})
    assert resp.status_code == 200
