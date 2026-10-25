"""
Tests for the provider registry: CRUD, key secrecy, connection checks, model
discovery, environment seeding and the private-URL policy.
"""

import logging

import pytest
from sqlalchemy import select

from llmwatch.config import settings
from llmwatch.db.models import Model, Provider
from llmwatch.llm import LLMClient
from llmwatch.providers import service
from llmwatch.security import secrets as secret_mod
from llmwatch.security.crypto import decrypt_secret
from tests.fake_llm import FakeProvider

RAW_KEY = "sk-live-0123456789abcdefWXYZ"


@pytest.fixture
def fake(monkeypatch):
    """Every provider client talks to one fake server; records the configs used."""
    fake = FakeProvider(models=["gpt-x", "gpt-y"])
    fake.configs = []

    def make_client(config):
        fake.configs.append(config)
        return LLMClient(config, http_client=fake.http_client())

    monkeypatch.setattr(service, "make_client", make_client)
    return fake


async def _create(client, account, **body):
    payload = {"name": "OpenAI", "preset": "openai", "api_key": RAW_KEY, **body}
    return await client.post("/providers", json=payload, headers=account.headers)


# ── Presets ─────────────────────────────────────────────────


async def test_presets_include_hosted_and_local_providers(client, make_account):
    owner = await make_account()
    presets = {
        p["id"]: p
        for p in (await client.get("/providers/presets", headers=owner.headers)).json()[
            "presets"
        ]
    }
    for preset_id in (
        "openai",
        "gemini",
        "openrouter",
        "groq",
        "together",
        "ollama",
        "vllm",
        "lmstudio",
        "custom",
    ):
        assert preset_id in presets
    assert presets["ollama"]["base_url"] == "http://localhost:11434/v1"
    assert presets["ollama"]["local"] is True
    assert presets["ollama"]["requires_api_key"] is False
    assert presets["openai"]["requires_api_key"] is True


# ── CRUD and key secrecy ────────────────────────────────────


async def test_create_uses_preset_url_and_masks_the_key(
    client, make_account, db_session
):
    owner = await make_account()
    resp = await _create(client, owner)

    assert resp.status_code == 201
    body = resp.json()
    assert body["base_url"] == "https://api.openai.com/v1"
    assert body["has_api_key"] is True
    assert body["api_key_masked"] == "••••WXYZ"
    assert body["preset_label"] == "OpenAI"
    assert RAW_KEY not in resp.text

    stored = (await db_session.execute(select(Provider))).scalar_one()
    assert stored.api_key_encrypted != RAW_KEY
    assert RAW_KEY not in stored.api_key_encrypted
    assert decrypt_secret(stored.api_key_encrypted) == RAW_KEY


async def test_the_key_never_appears_in_any_response_or_log(
    client, make_account, caplog
):
    owner = await make_account()
    with caplog.at_level(logging.DEBUG):
        created = (await _create(client, owner)).json()
        texts = [
            (await client.get("/providers", headers=owner.headers)).text,
            (
                await client.get(f"/providers/{created['id']}", headers=owner.headers)
            ).text,
            (
                await client.patch(
                    f"/providers/{created['id']}",
                    json={"enabled": False},
                    headers=owner.headers,
                )
            ).text,
        ]
    for text in texts:
        assert RAW_KEY not in text
        assert "api_key_encrypted" not in text
    assert RAW_KEY not in caplog.text


async def test_short_keys_get_no_hint(client, make_account):
    owner = await make_account()
    body = (await _create(client, owner, api_key="short")).json()
    assert body["api_key_masked"] == "••••"


async def test_local_provider_without_key(client, make_account):
    owner = await make_account()
    resp = await client.post(
        "/providers",
        json={"name": "Ollama", "preset": "ollama"},
        headers=owner.headers,
    )
    assert resp.status_code == 201
    assert resp.json()["has_api_key"] is False
    assert resp.json()["api_key_masked"] is None
    assert resp.json()["local"] is True


@pytest.mark.parametrize(
    "body,status",
    [
        ({"preset": "custom", "base_url": None}, 400),  # custom needs a URL
        ({"preset": "custom", "base_url": "ftp://x/v1"}, 400),
        ({"preset": "custom", "base_url": "http://user:pw@x/v1"}, 400),
        ({"preset": "nope"}, 400),
        ({"name": ""}, 422),
    ],
)
async def test_invalid_providers_rejected(client, make_account, body, status):
    owner = await make_account()
    resp = await _create(client, owner, **body)
    assert resp.status_code == status


async def test_duplicate_name_is_409(client, make_account):
    owner = await make_account()
    await _create(client, owner)
    assert (await _create(client, owner)).status_code == 409


async def test_update_keeps_replaces_and_clears_the_key(
    client, make_account, db_session
):
    owner = await make_account()
    pid = (await _create(client, owner)).json()["id"]
    url = f"/providers/{pid}"

    kept = await client.patch(url, json={"name": "Renamed"}, headers=owner.headers)
    assert kept.json()["has_api_key"] is True
    assert kept.json()["name"] == "Renamed"

    replaced = await client.patch(
        url, json={"api_key": "sk-new-key-0000000000NEW1"}, headers=owner.headers
    )
    assert replaced.json()["api_key_masked"] == "••••NEW1"

    cleared = await client.patch(url, json={"api_key": None}, headers=owner.headers)
    assert cleared.json()["has_api_key"] is False
    stored = await db_session.get(Provider, pid)
    await db_session.refresh(stored)
    assert stored.api_key_encrypted is None


async def test_changing_base_url_drops_the_stored_key(client, make_account, fake):
    """Otherwise an editor could redirect the provider and capture the key."""
    owner = await make_account()
    pid = (await _create(client, owner)).json()["id"]

    resp = await client.patch(
        f"/providers/{pid}",
        json={"base_url": "https://attacker.example/v1"},
        headers=owner.headers,
    )
    assert resp.json()["has_api_key"] is False

    await client.post(f"/providers/{pid}/test", headers=owner.headers)
    assert fake.configs[-1].api_key is None
    assert all(h.get("authorization") != f"Bearer {RAW_KEY}" for h in fake.headers)


async def test_base_url_change_with_new_key_keeps_the_new_key(client, make_account):
    owner = await make_account()
    pid = (await _create(client, owner)).json()["id"]
    resp = await client.patch(
        f"/providers/{pid}",
        json={
            "base_url": "https://proxy.example/v1",
            "api_key": "sk-proxy-key-123456789",
        },
        headers=owner.headers,
    )
    assert resp.json()["has_api_key"] is True
    assert resp.json()["base_url"] == "https://proxy.example/v1"


async def test_delete(client, make_account):
    owner = await make_account()
    pid = (await _create(client, owner)).json()["id"]
    assert (
        await client.delete(f"/providers/{pid}", headers=owner.headers)
    ).status_code == 204
    assert (
        await client.get(f"/providers/{pid}", headers=owner.headers)
    ).status_code == 404


# ── Access control ──────────────────────────────────────────


async def test_other_workspaces_cannot_see_or_touch_a_provider(
    client, make_account, fake
):
    alice = await make_account(workspace="A")
    bob = await make_account(workspace="B")
    pid = (await _create(client, alice)).json()["id"]

    assert (await client.get("/providers", headers=bob.headers)).json() == []
    for method, path, body in [
        ("get", f"/providers/{pid}", None),
        ("patch", f"/providers/{pid}", {"enabled": False}),
        ("delete", f"/providers/{pid}", None),
        ("post", f"/providers/{pid}/test", None),
        ("post", f"/providers/{pid}/discover", None),
    ]:
        resp = await client.request(method, path, json=body, headers=bob.headers)
        assert resp.status_code == 404, (method, path)
    assert fake.requests == []  # bob never caused a call with alice's key


async def test_members_can_read_and_test_but_not_manage(client, make_account, fake):
    owner = await make_account(workspace="A")
    member = await make_account(workspace_id=owner.workspace_id, role="member")
    pid = (await _create(client, owner)).json()["id"]

    assert (await client.get("/providers", headers=member.headers)).status_code == 200
    assert (
        await client.post(f"/providers/{pid}/test", headers=member.headers)
    ).status_code == 200
    assert (await _create(client, member, name="Mine")).status_code == 403
    assert (
        await client.patch(
            f"/providers/{pid}", json={"enabled": False}, headers=member.headers
        )
    ).status_code == 403
    assert (
        await client.delete(f"/providers/{pid}", headers=member.headers)
    ).status_code == 403


async def test_api_keys_can_read_but_not_manage_providers(client, make_account):
    owner = await make_account()
    key = (
        await client.post("/api-keys", json={"name": "ci"}, headers=owner.headers)
    ).json()["raw_key"]
    headers = {"X-API-Key": key}
    assert (await client.get("/providers", headers=headers)).status_code == 200
    resp = await client.post(
        "/providers", json={"name": "X", "preset": "ollama"}, headers=headers
    )
    assert resp.status_code == 403


# ── Connection test and discovery ───────────────────────────


async def test_connection_test_lists_models_with_the_decrypted_key(
    client, make_account, fake
):
    owner = await make_account()
    pid = (await _create(client, owner)).json()["id"]

    resp = await client.post(f"/providers/{pid}/test", headers=owner.headers)

    body = resp.json()
    assert body["ok"] is True
    assert body["model_count"] == 2
    assert body["models"] == ["gpt-x", "gpt-y"]
    assert fake.configs[-1].api_key == RAW_KEY
    assert fake.configs[-1].base_url == "https://api.openai.com/v1"
    assert fake.headers[-1]["authorization"] == f"Bearer {RAW_KEY}"
    assert RAW_KEY not in resp.text


async def test_connection_test_reports_provider_errors(client, make_account, fake):
    owner = await make_account()
    pid = (await _create(client, owner)).json()["id"]
    fake.models = []

    def unauthorized(request):
        import httpx

        return httpx.Response(401, json={"error": {"message": "invalid key"}})

    fake._handle = unauthorized  # type: ignore[method-assign]
    body = (await client.post(f"/providers/{pid}/test", headers=owner.headers)).json()
    assert body["ok"] is False
    assert body["error_kind"] == "auth"
    assert body["error"] == "invalid key"


async def test_undecryptable_key_fails_closed(client, make_account, fake, monkeypatch):
    owner = await make_account()
    pid = (await _create(client, owner)).json()["id"]

    monkeypatch.setattr(
        settings, "secret_key", "a-completely-different-secret-value-123"
    )
    secret_mod.reset_cache()
    try:
        # Sessions are signed with the secret too, so sign in again under the new one.
        from llmwatch.auth.jwt_handler import create_access_token

        token = create_access_token({"sub": owner.user_id})
        headers = {"Authorization": f"Bearer {token}"}
        body = (await client.post(f"/providers/{pid}/test", headers=headers)).json()
        listing = await client.get("/providers", headers=headers)
    finally:
        secret_mod.reset_cache()

    assert body["ok"] is False
    assert body["error_kind"] == "decryption"
    assert fake.requests == []  # nothing was sent with a garbage key
    assert listing.status_code == 200  # listing never needs to decrypt


async def test_discover_imports_new_models_once(client, make_account, fake, db_session):
    owner = await make_account()
    pid = (await _create(client, owner)).json()["id"]

    first = (
        await client.post(f"/providers/{pid}/discover", headers=owner.headers)
    ).json()
    assert first == {"discovered": ["gpt-x", "gpt-y"], "added": ["gpt-x", "gpt-y"]}
    fake.models = ["gpt-x", "gpt-y", "gpt-z"]
    second = (
        await client.post(f"/providers/{pid}/discover", headers=owner.headers)
    ).json()
    assert second["added"] == ["gpt-z"]

    models = (await db_session.execute(select(Model))).scalars().all()
    assert sorted(m.model_id for m in models) == ["gpt-x", "gpt-y", "gpt-z"]
    assert all(m.workspace_id == owner.workspace_id for m in models)
    assert all(m.input_price_per_mtok is None for m in models)  # hosted: unpriced


async def test_discovered_local_models_are_free_and_open_weights(
    client, make_account, fake, db_session
):
    owner = await make_account()
    pid = (
        await client.post(
            "/providers",
            json={"name": "Ollama", "preset": "ollama"},
            headers=owner.headers,
        )
    ).json()["id"]
    await client.post(f"/providers/{pid}/discover", headers=owner.headers)
    model = (await db_session.execute(select(Model))).scalars().first()
    assert model.input_price_per_mtok == 0.0
    assert model.open_weights is True


# ── Environment seeding ─────────────────────────────────────


@pytest.fixture
def env_keys(monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "sk-env-openai-0000000000AAAA")
    monkeypatch.setattr(settings, "ollama_base_url", "http://ollama:11434/v1")
    monkeypatch.setattr(settings, "google_api_key", "")
    monkeypatch.setattr(settings, "qwen_base_url", "")
    return monkeypatch


async def _providers(db_session, workspace_id):
    db_session.expire_all()
    rows = await db_session.execute(
        select(Provider).where(Provider.workspace_id == workspace_id)
    )
    return {p.name: p for p in rows.scalars()}


async def test_new_workspaces_get_env_providers(make_account, db_session, env_keys):
    acct = await make_account()
    providers = await _providers(db_session, acct.workspace_id)

    assert set(providers) == {"OpenAI", "Ollama"}
    assert all(p.managed_by_env for p in providers.values())
    assert decrypt_secret(providers["OpenAI"].api_key_encrypted).endswith("AAAA")
    assert providers["Ollama"].base_url == "http://ollama:11434/v1"
    assert providers["Ollama"].api_key_encrypted is None


async def test_env_sync_is_idempotent_and_follows_changes(
    make_account, db_session, env_keys
):
    acct = await make_account()
    await service.sync_env_providers_all(db_session)
    assert len(await _providers(db_session, acct.workspace_id)) == 2

    env_keys.setattr(settings, "openai_api_key", "sk-env-openai-rotated-0000BBBB")
    env_keys.setattr(settings, "ollama_base_url", "")
    await service.sync_env_providers_all(db_session)

    providers = await _providers(db_session, acct.workspace_id)
    assert decrypt_secret(providers["OpenAI"].api_key_encrypted).endswith("BBBB")
    assert providers["Ollama"].enabled is False  # env var removed: disabled, kept


async def test_env_sync_leaves_user_providers_with_the_same_name_alone(
    client, make_account, db_session, monkeypatch
):
    owner = await make_account()
    await _create(client, owner)  # user-created "OpenAI"
    monkeypatch.setattr(settings, "openai_api_key", "sk-env-openai-0000000000CCCC")
    await service.sync_env_providers_all(db_session)

    (provider,) = (await _providers(db_session, owner.workspace_id)).values()
    assert provider.managed_by_env is False
    assert decrypt_secret(provider.api_key_encrypted) == RAW_KEY


async def test_env_managed_providers_only_allow_toggling(
    client, make_account, env_keys
):
    owner = await make_account()
    listing = (await client.get("/providers", headers=owner.headers)).json()
    pid = next(p["id"] for p in listing if p["name"] == "OpenAI")

    assert (
        await client.patch(
            f"/providers/{pid}",
            json={"base_url": "https://x/v1"},
            headers=owner.headers,
        )
    ).status_code == 400
    assert (
        await client.patch(
            f"/providers/{pid}", json={"enabled": False}, headers=owner.headers
        )
    ).status_code == 200
    assert (
        await client.delete(f"/providers/{pid}", headers=owner.headers)
    ).status_code == 400


async def test_legacy_qwen_base_url_seeds_a_vllm_provider(
    make_account, db_session, monkeypatch
):
    monkeypatch.setattr(settings, "qwen_base_url", "http://vllm:8001/v1")
    monkeypatch.setattr(settings, "qwen_api_key", "")
    acct = await make_account()
    providers = await _providers(db_session, acct.workspace_id)
    assert providers["Qwen (vLLM)"].preset == "vllm"


# ── Private URL policy ──────────────────────────────────────


async def test_private_urls_allowed_by_default(client, make_account):
    owner = await make_account()
    resp = await _create(
        client,
        owner,
        name="Local",
        preset="custom",
        base_url="http://127.0.0.1:9000/v1",
    )
    assert resp.status_code == 201


async def test_private_urls_can_be_refused(client, make_account, monkeypatch):
    monkeypatch.setattr(settings, "provider_allow_private_urls", False)
    owner = await make_account()
    for url in (
        "http://127.0.0.1:9000/v1",
        "http://169.254.169.254/v1",
        "http://10.0.0.5/v1",
    ):
        resp = await _create(client, owner, name=url, preset="custom", base_url=url)
        assert resp.status_code == 400, url
        assert "not allowed" in resp.json()["error"]


async def test_env_providers_bypass_the_private_url_policy(
    make_account, db_session, monkeypatch
):
    """Operator-set URLs (e.g. Ollama on the docker network) are trusted."""
    monkeypatch.setattr(settings, "provider_allow_private_urls", False)
    monkeypatch.setattr(settings, "ollama_base_url", "http://127.0.0.1:11434/v1")
    acct = await make_account()
    assert "Ollama" in await _providers(db_session, acct.workspace_id)
