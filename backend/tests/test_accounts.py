"""
Tests for accounts on the SQL database: registration, login, signup policy, demo
seeding and workspace deletion.
"""

import pytest
from sqlalchemy import func, select

from llmwatch.config import settings
from llmwatch.db.models import ApiKey, LLMLog, User, Workspace
from llmwatch.services import accounts

PASSWORD = "correct-horse-battery"


async def _register(client, email="alice@example.com", **extra):
    body = {"email": email, "password": PASSWORD, "workspace_name": "Acme", **extra}
    return await client.post("/auth/register", json=body)


async def _login(client, email="alice@example.com", password=PASSWORD):
    return await client.post("/auth/login", json={"email": email, "password": password})


async def _count(session, model) -> int:
    return (await session.execute(select(func.count()).select_from(model))).scalar_one()


# ── Registration ────────────────────────────────────────────


async def test_register_creates_workspace_and_owner(client, db_session):
    resp = await _register(client)

    assert resp.status_code == 201
    body = resp.json()
    workspace = await db_session.get(Workspace, body["workspace_id"])
    assert workspace.name == "Acme"
    assert body["company_id"] == body["workspace_id"]  # deprecated alias
    user = (await db_session.execute(select(User))).scalar_one()
    assert user.workspace_id == workspace.id
    assert user.role == "owner"
    assert user.password_hash != PASSWORD


async def test_register_accepts_legacy_company_name(client, db_session):
    resp = await client.post(
        "/auth/register",
        json={"email": "a@example.com", "password": PASSWORD, "company_name": "Old"},
    )
    assert resp.status_code == 201
    workspace = await db_session.get(Workspace, resp.json()["workspace_id"])
    assert workspace.name == "Old"


async def test_register_requires_a_workspace_name(client):
    resp = await client.post(
        "/auth/register", json={"email": "a@example.com", "password": PASSWORD}
    )
    assert resp.status_code == 422


async def test_duplicate_email_is_409_case_insensitively(client):
    assert (await _register(client, "Alice@Example.com")).status_code == 201
    resp = await _register(client, "ALICE@example.com")
    assert resp.status_code == 409
    assert resp.json()["code"] == "CONFLICT"


async def test_password_longer_than_72_bytes_rejected(client):
    resp = await client.post(
        "/auth/register",
        json={"email": "a@example.com", "password": "é" * 37, "workspace_name": "A"},
    )
    assert resp.status_code == 422


async def test_short_password_rejected(client):
    resp = await client.post(
        "/auth/register",
        json={"email": "a@example.com", "password": "short", "workspace_name": "A"},
    )
    assert resp.status_code == 422


async def test_signups_closed_still_allow_the_first_account(client, monkeypatch):
    monkeypatch.setattr(settings, "allow_signup", False)

    assert (await _register(client, "first@example.com")).status_code == 201
    resp = await _register(client, "second@example.com")
    assert resp.status_code == 403
    assert "disabled" in resp.json()["error"].lower()


# ── Login ───────────────────────────────────────────────────


async def test_login_returns_a_working_token(client):
    await _register(client)
    resp = await _login(client)

    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == settings.jwt_expire_hours * 3600
    me = await client.get(
        "/auth/me", headers={"Authorization": f"Bearer {body['access_token']}"}
    )
    assert me.json()["user"]["email"] == "alice@example.com"


async def test_login_email_is_case_insensitive(client):
    await _register(client)
    assert (await _login(client, email="ALICE@example.com")).status_code == 200


@pytest.mark.parametrize(
    "email,password",
    [("alice@example.com", "wrong-password"), ("nobody@example.com", PASSWORD)],
)
async def test_bad_credentials_are_401_with_the_same_message(client, email, password):
    await _register(client)
    resp = await _login(client, email=email, password=password)
    assert resp.status_code == 401
    assert resp.json()["error"] == "Invalid credentials"


async def test_unknown_email_still_runs_bcrypt(monkeypatch, db_session):
    """Timing: a missing account must cost a bcrypt check like a wrong password."""
    calls = []
    real = accounts.verify_password
    monkeypatch.setattr(
        accounts, "verify_password", lambda p, h: calls.append(h) or real(p, h)
    )
    with pytest.raises(Exception):
        await accounts.authenticate(db_session, "nobody@example.com", PASSWORD)
    assert calls == [accounts._DUMMY_HASH]


async def test_disabled_account_cannot_log_in(client, db_session):
    await _register(client)
    user = (await db_session.execute(select(User))).scalar_one()
    user.is_active = False
    await db_session.commit()

    resp = await _login(client)
    assert resp.status_code == 401
    assert "disabled" in resp.json()["error"].lower()


async def test_oauth2_form_token_endpoint(client):
    await _register(client)
    resp = await client.post(
        "/auth/token", data={"username": "alice@example.com", "password": PASSWORD}
    )
    assert resp.status_code == 200
    assert "access_token" in resp.json()


# ── Demo mode ───────────────────────────────────────────────


async def test_demo_account_is_seeded_once_and_can_log_in(client, db_session):
    await accounts.ensure_demo_account(db_session)
    await accounts.ensure_demo_account(db_session)  # idempotent

    assert await _count(db_session, User) == 1
    resp = await _login(client, settings.demo_email, settings.demo_password)
    assert resp.status_code == 200


async def test_demo_credentials_do_not_work_without_seeding(client):
    """Regression: demo login used to bypass the database entirely."""
    resp = await _login(client, "admin@company.com", "admin123")
    assert resp.status_code == 401
    resp = await _login(client, settings.demo_email, settings.demo_password)
    assert resp.status_code == 401


async def test_demo_seeding_runs_at_startup(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient

    from llmwatch.db.engine import dispose_engine
    from llmwatch.main import app

    monkeypatch.setattr(
        settings, "database_url", f"sqlite+aiosqlite:///{tmp_path / 'demo.db'}"
    )
    monkeypatch.setattr(settings, "demo_mode", True)
    await dispose_engine()
    with TestClient(app) as http:
        resp = http.post(
            "/auth/login",
            json={"email": settings.demo_email, "password": settings.demo_password},
        )
        assert resp.status_code == 200


# ── Workspace deletion ──────────────────────────────────────


async def test_owner_can_delete_workspace_and_everything_in_it(
    client, make_account, db_session
):
    owner = await make_account(workspace="Doomed")
    member = await make_account(workspace_id=owner.workspace_id, role="member")
    other = await make_account(workspace="Survivor")
    await client.post("/api-keys", json={"name": "k"}, headers=owner.headers)
    db_session.add_all(
        [
            LLMLog(workspace_id=owner.workspace_id, model_name="m"),
            LLMLog(workspace_id=other.workspace_id, model_name="m"),
        ]
    )
    await db_session.commit()

    resp = await client.request(
        "DELETE",
        "/workspaces/current",
        json={"confirm_name": "Doomed"},
        headers=owner.headers,
    )
    assert resp.status_code == 204

    db_session.expire_all()
    assert await db_session.get(Workspace, owner.workspace_id) is None
    assert await db_session.get(User, member.user_id) is None
    assert await _count(db_session, ApiKey) == 0
    assert await _count(db_session, LLMLog) == 1  # the other workspace's
    # Old sessions stop working immediately.
    assert (await client.get("/auth/me", headers=owner.headers)).status_code == 401
    assert (await client.get("/auth/me", headers=other.headers)).status_code == 200


async def test_workspace_delete_requires_matching_name(
    client, make_account, db_session
):
    owner = await make_account(workspace="Keep")
    resp = await client.request(
        "DELETE",
        "/workspaces/current",
        json={"confirm_name": "keep"},
        headers=owner.headers,
    )
    assert resp.status_code == 400
    assert await db_session.get(Workspace, owner.workspace_id) is not None


async def test_member_cannot_delete_workspace(client, make_account, db_session):
    owner = await make_account(workspace="Keep")
    member = await make_account(workspace_id=owner.workspace_id, role="member")
    resp = await client.request(
        "DELETE",
        "/workspaces/current",
        json={"confirm_name": "Keep"},
        headers=member.headers,
    )
    assert resp.status_code == 403
    assert await db_session.get(Workspace, owner.workspace_id) is not None


async def test_api_key_cannot_delete_workspace(client, make_account, db_session):
    owner = await make_account(workspace="Keep")
    key = (
        await client.post("/api-keys", json={"name": "k"}, headers=owner.headers)
    ).json()
    resp = await client.request(
        "DELETE",
        "/workspaces/current",
        json={"confirm_name": "Keep"},
        headers={"X-API-Key": key["raw_key"]},
    )
    assert resp.status_code == 403
    assert await db_session.get(Workspace, owner.workspace_id) is not None


async def test_get_current_workspace(client, make_account):
    owner = await make_account(workspace="Acme")
    resp = await client.get("/workspaces/current", headers=owner.headers)
    assert resp.status_code == 200
    assert resp.json()["name"] == "Acme"
