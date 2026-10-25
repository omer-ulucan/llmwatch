"""
Tests for the model catalogue (/models) and model reference resolution.
"""

import pytest
from sqlalchemy import func, select

from llmwatch.config import settings
from llmwatch.db.models import Model
from llmwatch.exceptions import ValidationException
from llmwatch.providers.models import resolve_model


async def _provider(client, account, name="OpenAI", preset="openai", **extra):
    body = {"name": name, "preset": preset, "api_key": "sk-test-key-000000001", **extra}
    resp = await client.post("/providers", json=body, headers=account.headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


async def _model(client, account, provider_id, model_id, **extra):
    body = {"provider_id": provider_id, "model_id": model_id, **extra}
    resp = await client.post("/models", json=body, headers=account.headers)
    assert resp.status_code == 201, resp.text
    return resp.json()


@pytest.fixture
async def catalog(client, make_account):
    """Owner with OpenAI (2 models) and Ollama (1 model)."""
    owner = await make_account()
    openai = await _provider(client, owner)
    ollama = await _provider(
        client, owner, name="Ollama", preset="ollama", api_key=None
    )
    gpt = await _model(
        client,
        owner,
        openai["id"],
        "gpt-x",
        display_name="GPT X",
        context_window=128000,
        capabilities={"tools": True, "json_mode": True},
        input_price_per_mtok=2.5,
        output_price_per_mtok=10.0,
    )
    mini = await _model(client, owner, openai["id"], "gpt-x-mini")
    llama = await _model(
        client,
        owner,
        ollama["id"],
        "llama3.2",
        open_weights=True,
        input_price_per_mtok=0,
        output_price_per_mtok=0,
    )
    return (
        owner,
        {"openai": openai, "ollama": ollama},
        {"gpt": gpt, "mini": mini, "llama": llama},
    )


# ── Catalogue ───────────────────────────────────────────────


async def test_catalog_is_grouped_by_provider(client, catalog):
    owner, providers, models = catalog
    body = (await client.get("/models", headers=owner.headers)).json()

    groups = {g["provider"]["name"]: g for g in body["groups"]}
    assert set(groups) == {"OpenAI", "Ollama"}
    assert [m["model_id"] for m in groups["OpenAI"]["models"]] == [
        "gpt-x",
        "gpt-x-mini",
    ]
    assert "sk-test-key" not in str(body)  # provider keys never leak

    gpt = groups["OpenAI"]["models"][0]
    assert gpt["ref"] == "OpenAI/gpt-x"
    assert gpt["display_name"] == "GPT X"
    assert gpt["context_window"] == 128000
    assert gpt["capabilities"] == {
        "tools": True,
        "vision": False,
        "reasoning": False,
        "json_mode": True,
    }
    assert gpt["input_price_per_mtok"] == 2.5
    assert gpt["priced"] is True
    assert gpt["local"] is False


async def test_unpriced_model_is_flagged(client, catalog):
    owner, _, models = catalog
    assert models["mini"]["priced"] is False
    assert models["mini"]["input_price_per_mtok"] is None
    assert models["llama"]["priced"] is True  # explicitly $0
    assert models["llama"]["local"] is True


@pytest.mark.parametrize(
    "params,expected",
    [
        ({"open_weights": "true"}, ["llama3.2"]),
        ({"local": "true"}, ["llama3.2"]),
        ({"local": "false"}, ["gpt-x", "gpt-x-mini"]),
        ({"q": "MINI"}, ["gpt-x-mini"]),
        ({"q": "ollama"}, ["llama3.2"]),
    ],
)
async def test_catalog_filters(client, catalog, params, expected):
    owner, _, _ = catalog
    body = (await client.get("/models", params=params, headers=owner.headers)).json()
    ids = [m["model_id"] for g in body["groups"] for m in g["models"]]
    assert ids == expected


async def test_available_only_hides_disabled_models_and_providers(client, catalog):
    owner, providers, models = catalog
    await client.patch(
        f"/models/{models['mini']['id']}",
        json={"enabled": False},
        headers=owner.headers,
    )
    await client.patch(
        f"/providers/{providers['ollama']['id']}",
        json={"enabled": False},
        headers=owner.headers,
    )
    body = (
        await client.get(
            "/models", params={"available_only": "true"}, headers=owner.headers
        )
    ).json()
    ids = [m["model_id"] for g in body["groups"] for m in g["models"]]
    assert ids == ["gpt-x"]

    everything = (await client.get("/models", headers=owner.headers)).json()
    flags = {
        m["model_id"]: m["available"] for g in everything["groups"] for m in g["models"]
    }
    assert flags == {"gpt-x": True, "gpt-x-mini": False, "llama3.2": False}


# ── Editing ─────────────────────────────────────────────────


async def test_prices_and_metadata_are_editable(client, catalog):
    owner, _, models = catalog
    url = f"/models/{models['gpt']['id']}"
    resp = await client.patch(
        url,
        json={
            "input_price_per_mtok": 1.25,
            "display_name": "GPT X (cheap)",
            "capabilities": {"vision": True},
        },
        headers=owner.headers,
    )
    body = resp.json()
    assert body["input_price_per_mtok"] == 1.25
    assert body["output_price_per_mtok"] == 10.0  # untouched
    assert body["display_name"] == "GPT X (cheap)"
    assert body["capabilities"]["vision"] is True

    unpriced = await client.patch(
        url,
        json={"input_price_per_mtok": None, "output_price_per_mtok": None},
        headers=owner.headers,
    )
    assert unpriced.json()["priced"] is False


async def test_negative_prices_rejected(client, catalog):
    owner, _, models = catalog
    resp = await client.patch(
        f"/models/{models['gpt']['id']}",
        json={"input_price_per_mtok": -1},
        headers=owner.headers,
    )
    assert resp.status_code == 422


async def test_duplicate_model_on_same_provider_is_409(client, catalog):
    owner, providers, _ = catalog
    resp = await client.post(
        "/models",
        json={"provider_id": providers["openai"]["id"], "model_id": "gpt-x"},
        headers=owner.headers,
    )
    assert resp.status_code == 409


async def test_exactly_one_default_model(client, catalog, db_session):
    owner, _, models = catalog
    for key in ("gpt", "llama", "mini"):
        resp = await client.patch(
            f"/models/{models[key]['id']}",
            json={"is_default": True},
            headers=owner.headers,
        )
        assert resp.status_code == 200
        assert resp.json()["is_default"] is True

    defaults = (
        await db_session.execute(
            select(func.count()).select_from(Model).where(Model.is_default.is_(True))
        )
    ).scalar_one()
    assert defaults == 1
    body = (await client.get("/models", headers=owner.headers)).json()
    assert body["default_model_id"] == models["mini"]["id"]


async def test_create_as_default(client, catalog):
    owner, providers, models = catalog
    new = await _model(
        client, owner, providers["openai"]["id"], "gpt-z", is_default=True
    )
    body = (await client.get("/models", headers=owner.headers)).json()
    assert body["default_model_id"] == new["id"]


async def test_disabling_the_default_unsets_it(client, catalog):
    owner, _, models = catalog
    url = f"/models/{models['gpt']['id']}"
    await client.patch(url, json={"is_default": True}, headers=owner.headers)
    resp = await client.patch(url, json={"enabled": False}, headers=owner.headers)
    assert resp.json()["is_default"] is False


async def test_delete_model(client, catalog):
    owner, _, models = catalog
    assert (
        await client.delete(f"/models/{models['mini']['id']}", headers=owner.headers)
    ).status_code == 204
    body = (await client.get("/models", headers=owner.headers)).json()
    ids = [m["model_id"] for g in body["groups"] for m in g["models"]]
    assert "gpt-x-mini" not in ids


async def test_deleting_a_provider_deletes_its_models(client, catalog, db_session):
    owner, providers, _ = catalog
    await client.delete(
        f"/providers/{providers['openai']['id']}", headers=owner.headers
    )
    count = (
        await db_session.execute(select(func.count()).select_from(Model))
    ).scalar_one()
    assert count == 1


async def test_members_read_owners_write(client, catalog, make_account):
    owner, providers, models = catalog
    member = await make_account(workspace_id=owner.workspace_id, role="member")
    assert (await client.get("/models", headers=member.headers)).status_code == 200
    assert (
        await client.patch(
            f"/models/{models['gpt']['id']}",
            json={"enabled": False},
            headers=member.headers,
        )
    ).status_code == 403
    assert (
        await client.post(
            "/models",
            json={"provider_id": providers["openai"]["id"], "model_id": "x"},
            headers=member.headers,
        )
    ).status_code == 403


async def test_workspace_isolation(client, catalog, make_account):
    owner, providers, models = catalog
    other = await make_account(workspace="Other")
    assert (await client.get("/models", headers=other.headers)).json()["groups"] == []
    assert (
        await client.patch(
            f"/models/{models['gpt']['id']}",
            json={"enabled": False},
            headers=other.headers,
        )
    ).status_code == 404
    # Can't attach a model to another workspace's provider either.
    other_owner_resp = await client.post(
        "/models",
        json={"provider_id": providers["openai"]["id"], "model_id": "stolen"},
        headers=other.headers,
    )
    assert other_owner_resp.status_code == 404


# ── Resolution ──────────────────────────────────────────────


async def test_resolve_by_id_pair_unique_model_id_and_default(
    client, catalog, db_session
):
    owner, _, models = catalog
    ws = owner.workspace_id
    assert (
        await resolve_model(db_session, ws, models["gpt"]["id"])
    ).model.model_id == "gpt-x"
    assert (
        await resolve_model(db_session, ws, "OpenAI/gpt-x-mini")
    ).model.model_id == "gpt-x-mini"
    resolved = await resolve_model(db_session, ws, "llama3.2")
    assert resolved.provider.name == "Ollama"
    assert resolved.label == "Ollama/llama3.2"

    with pytest.raises(ValidationException, match="No default"):
        await resolve_model(db_session, ws, "default")
    await client.patch(
        f"/models/{models['llama']['id']}",
        json={"is_default": True},
        headers=owner.headers,
    )
    db_session.expire_all()
    assert (await resolve_model(db_session, ws, "default")).model.model_id == "llama3.2"


async def test_resolve_ambiguous_model_id_lists_choices(client, catalog, db_session):
    owner, providers, _ = catalog
    other = await _provider(client, owner, name="Router", preset="openrouter")
    await _model(client, owner, other["id"], "gpt-x")
    with pytest.raises(ValidationException, match="OpenAI/gpt-x.*Router/gpt-x"):
        await resolve_model(db_session, owner.workspace_id, "gpt-x")


async def test_resolve_refuses_disabled_and_unknown(client, catalog, db_session):
    owner, providers, models = catalog
    await client.patch(
        f"/providers/{providers['ollama']['id']}",
        json={"enabled": False},
        headers=owner.headers,
    )
    db_session.expire_all()
    with pytest.raises(ValidationException, match="Unknown or disabled"):
        await resolve_model(db_session, owner.workspace_id, "llama3.2")
    with pytest.raises(ValidationException, match="Unknown or disabled"):
        await resolve_model(db_session, owner.workspace_id, "nope")


async def test_resolve_never_crosses_workspaces(
    client, catalog, make_account, db_session
):
    owner, _, models = catalog
    other = await make_account(workspace="Other")
    with pytest.raises(ValidationException):
        await resolve_model(db_session, other.workspace_id, models["gpt"]["id"])


async def test_resolve_endpoint(client, catalog):
    owner, _, _ = catalog
    resp = await client.get(
        "/models/resolve", params={"ref": "OpenAI/gpt-x"}, headers=owner.headers
    )
    assert resp.json()["model_id"] == "gpt-x"
    bad = await client.get(
        "/models/resolve", params={"ref": "qwen"}, headers=owner.headers
    )
    assert bad.status_code == 400
    assert "isn't configured" in bad.json()["error"]


# ── Legacy aliases ──────────────────────────────────────────


async def test_legacy_aliases_map_to_env_seeded_models(
    make_account, db_session, monkeypatch
):
    """Backward compatibility: old clients sending "qwen"/"gemini" keep working."""
    monkeypatch.setattr(settings, "google_api_key", "AIza-test-key-0000000")
    monkeypatch.setattr(settings, "qwen_base_url", "http://vllm:8001/v1")
    acct = await make_account()

    gemini = await resolve_model(db_session, acct.workspace_id, "gemini")
    assert gemini.provider.preset == "gemini"
    assert gemini.model.model_id == settings.gemini_model
    assert gemini.model.input_price_per_mtok == 0.50
    assert gemini.model.output_price_per_mtok == 3.00

    qwen = await resolve_model(db_session, acct.workspace_id, "qwen")
    assert qwen.provider.name == "Qwen (vLLM)"
    assert qwen.model.model_id == settings.qwen_model


async def test_legacy_alias_uses_a_user_configured_provider(
    client, make_account, db_session
):
    owner = await make_account()
    gem = await _provider(client, owner, name="My Gemini", preset="gemini")
    await _model(client, owner, gem["id"], "gemini-other")
    resolved = await resolve_model(db_session, owner.workspace_id, "gemini")
    assert resolved.model.model_id == "gemini-other"


async def test_legacy_alias_not_configured_explains_what_to_do(
    make_account, db_session
):
    acct = await make_account()
    with pytest.raises(ValidationException, match="Gemini provider"):
        await resolve_model(db_session, acct.workspace_id, "gemini")
    with pytest.raises(ValidationException, match="vLLM provider"):
        await resolve_model(db_session, acct.workspace_id, "qwen")
