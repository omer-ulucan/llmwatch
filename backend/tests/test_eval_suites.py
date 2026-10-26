"""
Tests for eval suites: templates, the file format, storage with immutable versions,
import/export and the API.
"""

import json

import pytest
import yaml

from llmwatch.evals.messages import build_messages
from llmwatch.evals.schema import (
    SuiteDefinition,
    SuiteFormatError,
    dump_suite,
    parse_suite,
)
from llmwatch.evals.template import TemplateError, render, variables

SUITE_YAML = """
name: support-triage
description: Route tickets
system_prompt: You triage tickets for {{ company }}.
prompt: |
  Classify into billing, bug or account.
  Ticket: {{ ticket }}
assert:
  - type: latency_under
    value: 5000
cases:
  - id: refund
    vars: {ticket: "I was charged twice", company: Acme}
    expected: billing
    assert:
      - type: contains
        value: billing
        case_sensitive: false
    tags: [billing]
  - vars: {ticket: "App crashes on login", company: Acme}
    expected: bug
"""


def _definition(**overrides) -> dict:
    data = yaml.safe_load(SUITE_YAML)
    data.update(overrides)
    return data


# ── Templates ───────────────────────────────────────────────


def test_render_with_and_without_spaces():
    assert render("Hi {{name}} / {{ name }}", {"name": "Ada"}) == "Hi Ada / Ada"


def test_render_dotted_and_non_string_values():
    out = render(
        "{{ t.subject }} {{ n }} {{ tags }}",
        {"t": {"subject": "S"}, "n": 3, "tags": ["a"]},
    )
    assert out == 'S 3 ["a"]'


def test_missing_variables_are_an_error_not_blank():
    with pytest.raises(TemplateError, match="ticket, user.name"):
        render("{{ ticket }} {{ user.name }} {{ ticket }}", {"user": {}})


def test_templates_cannot_execute_anything():
    # Jinja-style expressions are not placeholders and are left as-is.
    template = "{{ 7*7 }} {% for x in y %} {{ __import__('os') }}"
    assert render(template, {}) == template


def test_variables_lists_top_level_names_once():
    assert variables("{{ a }} {{ b.c }} {{a}}") == ["a", "b"]


def test_build_messages():
    definition = SuiteDefinition.model_validate(_definition())
    messages = build_messages(definition, {"ticket": "X", "company": "Acme"})
    assert messages == [
        {"role": "system", "content": "You triage tickets for Acme."},
        {
            "role": "user",
            "content": "Classify into billing, bug or account.\nTicket: X\n",
        },
    ]


# ── File format ─────────────────────────────────────────────


def test_parse_assigns_ids_and_keeps_assertion_options():
    suite = parse_suite(SUITE_YAML)
    assert [c.id for c in suite.cases] == ["refund", "case-2"]
    assertion = suite.cases[0].assertions[0]
    assert assertion.type == "contains"
    assert assertion.value == "billing"
    assert assertion.config() == {"case_sensitive": False}
    assert suite.default_assertions[0].value == 5000


def test_cases_must_provide_every_template_variable():
    data = _definition()
    data["cases"][1]["vars"] = {"ticket": "x"}  # no company
    with pytest.raises(SuiteFormatError, match="case-2.*missing vars: company"):
        parse_suite(json.dumps(data), "json")


def test_duplicate_case_ids_rejected():
    data = _definition()
    data["cases"][1]["id"] = "refund"
    with pytest.raises(SuiteFormatError, match="duplicate case id"):
        parse_suite(json.dumps(data), "json")


@pytest.mark.parametrize(
    "text,message",
    [
        ("name: [unclosed", "Could not parse"),
        ("- just\n- a list\n", "must be a mapping"),
        ("name: x\nprompt: hi\n", "cases"),
        ("name: x\nprompt: hi\ncases: []\n", "cases"),
        ("name: x\nprompt: hi\ncases:\n  - vars: {}\n    bogus: 1\n", "bogus"),
    ],
)
def test_invalid_files(text, message):
    with pytest.raises(SuiteFormatError, match=message):
        parse_suite(text)


def test_yaml_is_loaded_safely():
    evil = "name: !!python/object/apply:os.system ['echo pwned']\nprompt: x\ncases: [{vars: {}}]\n"
    with pytest.raises(SuiteFormatError):
        parse_suite(evil)


@pytest.mark.parametrize("fmt", ["yaml", "json"])
def test_dump_and_parse_round_trip(fmt):
    original = parse_suite(SUITE_YAML)
    again = parse_suite(dump_suite(original, fmt), fmt)
    assert again.to_document() == original.to_document()


# ── API: create, read, versions ─────────────────────────────


async def _create(client, account, **overrides):
    resp = await client.post(
        "/evals/suites", json=_definition(**overrides), headers=account.headers
    )
    assert resp.status_code == 201, resp.text
    return resp.json()


async def test_create_and_get(client, make_account):
    acct = await make_account()
    created = await _create(client, acct)

    assert created["name"] == "support-triage"
    assert created["version"] == 1
    assert created["case_count"] == 2
    assert created["definition"]["cases"][1]["id"] == "case-2"

    listing = (await client.get("/evals/suites", headers=acct.headers)).json()["suites"]
    assert [(s["name"], s["case_count"], s["latest_version"]) for s in listing] == [
        ("support-triage", 2, 1)
    ]


async def test_invalid_definition_is_422(client, make_account):
    acct = await make_account()
    data = _definition()
    data["cases"][0]["vars"] = {}
    resp = await client.post("/evals/suites", json=data, headers=acct.headers)
    assert resp.status_code == 422
    assert "missing vars" in resp.text


async def test_duplicate_suite_name_is_409(client, make_account):
    acct = await make_account()
    await _create(client, acct)
    resp = await client.post("/evals/suites", json=_definition(), headers=acct.headers)
    assert resp.status_code == 409


async def test_editing_creates_a_new_immutable_version(client, make_account):
    acct = await make_account()
    suite = await _create(client, acct)
    url = f"/evals/suites/{suite['id']}"

    changed = _definition(prompt="New prompt: {{ ticket }} for {{ company }}")
    v2 = (await client.put(url, json=changed, headers=acct.headers)).json()
    assert v2["created_version"] is True
    assert v2["version"] == 2
    assert [v["version"] for v in v2["versions"]] == [2, 1]

    v1 = (await client.get(url, params={"version": 1}, headers=acct.headers)).json()
    assert v1["definition"]["prompt"].startswith("Classify")  # untouched
    assert v1["version_id"] != v2["version_id"]


async def test_saving_identical_content_does_not_create_a_version(client, make_account):
    acct = await make_account()
    suite = await _create(client, acct)
    url = f"/evals/suites/{suite['id']}"

    same = (
        await client.put(
            url, json=_definition(description="Only text changed"), headers=acct.headers
        )
    ).json()

    assert same["created_version"] is False
    assert same["version"] == 1
    assert same["description"] == "Only text changed"


async def test_rename_to_an_existing_name_is_409(client, make_account):
    acct = await make_account()
    await _create(client, acct)
    other = await _create(client, acct, name="other")
    resp = await client.put(
        f"/evals/suites/{other['id']}", json=_definition(), headers=acct.headers
    )
    assert resp.status_code == 409


async def test_delete_suite(client, make_account):
    acct = await make_account()
    suite = await _create(client, acct)
    assert (
        await client.delete(f"/evals/suites/{suite['id']}", headers=acct.headers)
    ).status_code == 204
    assert (
        await client.get(f"/evals/suites/{suite['id']}", headers=acct.headers)
    ).status_code == 404


# ── Import / export ─────────────────────────────────────────


async def test_import_creates_then_versions_by_name(client, make_account):
    acct = await make_account()
    first = (
        await client.post(
            "/evals/suites/import", json={"content": SUITE_YAML}, headers=acct.headers
        )
    ).json()
    assert first["created_suite"] is True
    assert first["version"] == 1

    again = (
        await client.post(
            "/evals/suites/import", json={"content": SUITE_YAML}, headers=acct.headers
        )
    ).json()
    assert again["created_suite"] is False
    assert again["created_version"] is False

    edited = SUITE_YAML.replace("I was charged twice", "Double charge")
    third = (
        await client.post(
            "/evals/suites/import", json={"content": edited}, headers=acct.headers
        )
    ).json()
    assert third["created_version"] is True
    assert third["version"] == 2


async def test_import_errors_are_400(client, make_account):
    acct = await make_account()
    resp = await client.post(
        "/evals/suites/import", json={"content": "name: [oops"}, headers=acct.headers
    )
    assert resp.status_code == 400
    assert "Could not parse" in resp.json()["error"]


@pytest.mark.parametrize("fmt", ["yaml", "json"])
async def test_export_round_trips(client, make_account, fmt):
    acct = await make_account()
    suite = await _create(client, acct)
    resp = await client.get(
        f"/evals/suites/{suite['id']}/export",
        params={"format": fmt},
        headers=acct.headers,
    )
    assert resp.status_code == 200
    assert "attachment" in resp.headers["content-disposition"]
    assert (
        parse_suite(resp.text, fmt).to_document()
        == parse_suite(SUITE_YAML).to_document()
    )


async def test_export_a_specific_version(client, make_account):
    acct = await make_account()
    suite = await _create(client, acct)
    await client.put(
        f"/evals/suites/{suite['id']}",
        json=_definition(prompt="v2 {{ ticket }} {{ company }}"),
        headers=acct.headers,
    )
    resp = await client.get(
        f"/evals/suites/{suite['id']}/export",
        params={"version": 1},
        headers=acct.headers,
    )
    assert "Classify" in resp.text


# ── Preview ─────────────────────────────────────────────────


async def test_preview_renders_a_case(client, make_account):
    acct = await make_account()
    suite = await _create(client, acct)
    body = (
        await client.post(
            f"/evals/suites/{suite['id']}/preview",
            json={"case_id": "case-2"},
            headers=acct.headers,
        )
    ).json()
    assert body["case_id"] == "case-2"
    assert "App crashes on login" in body["messages"][-1]["content"]


async def test_preview_with_custom_vars_missing_one_is_400(client, make_account):
    acct = await make_account()
    suite = await _create(client, acct)
    resp = await client.post(
        f"/evals/suites/{suite['id']}/preview",
        json={"vars": {"ticket": "x"}},
        headers=acct.headers,
    )
    assert resp.status_code == 400
    assert "company" in resp.json()["error"]


# ── Access ──────────────────────────────────────────────────


async def test_suites_are_isolated_per_workspace(client, make_account):
    alice = await make_account(workspace="A")
    bob = await make_account(workspace="B")
    suite = await _create(client, alice)

    assert (await client.get("/evals/suites", headers=bob.headers)).json()[
        "suites"
    ] == []
    for method, path in [
        ("get", f"/evals/suites/{suite['id']}"),
        ("put", f"/evals/suites/{suite['id']}"),
        ("delete", f"/evals/suites/{suite['id']}"),
        ("get", f"/evals/suites/{suite['id']}/export"),
    ]:
        resp = await client.request(
            method, path, json=_definition(), headers=bob.headers
        )
        assert resp.status_code == 404, (method, path)
    # Same name in another workspace is fine.
    await _create(client, bob)


async def test_api_keys_can_push_suites(client, make_account):
    """The CLI imports suites with an API key."""
    acct = await make_account()
    key = (
        await client.post("/api-keys", json={"name": "ci"}, headers=acct.headers)
    ).json()["raw_key"]
    resp = await client.post(
        "/evals/suites/import", json={"content": SUITE_YAML}, headers={"X-API-Key": key}
    )
    assert resp.status_code == 200
