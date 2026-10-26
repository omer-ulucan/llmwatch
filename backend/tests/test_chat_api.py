"""
Tests for /chat/completions and /chat/stream against the model registry and a
fake OpenAI-compatible provider.
"""

import json
from unittest.mock import patch

import httpx
import pytest

from llmwatch.config import settings


async def _logs(client, account):
    return (await client.get("/analytics/logs", headers=account.headers)).json()[
        "items"
    ]


@pytest.fixture
def account_with(make_account, add_model):
    async def _new(**model_kwargs):
        account = await make_account()
        await add_model(account, **model_kwargs)
        return account

    return _new


# ── Non-streaming ───────────────────────────────────────────


async def test_completion_uses_the_registry_model(client, account_with, fake_llm):
    acct = await account_with()
    fake_llm.reply("hi!", usage=(1000, 500))

    resp = await client.post(
        "/chat/completions",
        json={"prompt": "hello", "model": "fake-model"},
        headers=acct.headers,
    )

    assert resp.status_code == 200
    body = resp.json()
    assert body["response"] == "hi!"
    assert body["model_used"] == "Fake/fake-model"
    assert body["input_tokens"] == 1000
    assert body["output_tokens"] == 500
    assert body["usage_reported"] is True
    # $1/1M input, $2/1M output
    assert body["cost_usd"] == pytest.approx(0.001 + 0.001)
    assert body["priced"] is True
    assert body["finish_reason"] == "stop"
    assert fake_llm.requests[-1]["model"] == "fake-model"


async def test_messages_system_prompt_and_params(client, account_with, fake_llm):
    acct = await account_with()
    await client.post(
        "/chat/completions",
        json={
            "model": "fake-model",
            "system_prompt": "Be brief.",
            "messages": [
                {"role": "user", "content": "Hi"},
                {"role": "assistant", "content": "Hello!"},
            ],
            "prompt": "What's 2+2?",
            "temperature": 0.2,
            "max_tokens": 50,
        },
        headers=acct.headers,
    )
    sent = fake_llm.requests[-1]
    assert sent["messages"] == [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Hi"},
        {"role": "assistant", "content": "Hello!"},
        {"role": "user", "content": "What's 2+2?"},
    ]
    assert sent["temperature"] == 0.2
    assert sent["max_tokens"] == 50
    assert "top_p" not in sent


async def test_unpriced_model_reports_priced_false(client, account_with, fake_llm):
    acct = await account_with(input_price=None, output_price=None)
    body = (
        await client.post(
            "/chat/completions",
            json={"prompt": "hi", "model": "fake-model"},
            headers=acct.headers,
        )
    ).json()
    assert body["priced"] is False
    assert body["cost_usd"] == 0.0


async def test_missing_usage_is_reported_as_such(client, account_with, fake_llm):
    acct = await account_with()
    fake_llm.reply("hi", usage=None)
    body = (
        await client.post(
            "/chat/completions",
            json={"prompt": "hi", "model": "fake-model"},
            headers=acct.headers,
        )
    ).json()
    assert body["usage_reported"] is False
    assert body["input_tokens"] == 0


@pytest.mark.parametrize(
    "preset,supports_reasoning,thinking,expected_effort,no_think",
    [
        ("gemini", False, True, "high", False),
        ("gemini", False, False, "low", False),
        ("openai", True, True, "high", False),
        ("openai", True, False, None, False),
        ("openai", False, True, None, False),  # never sent to non-reasoning models
        ("vllm", True, False, None, True),
        ("vllm", True, True, None, False),
        # Ollama thinks by default; "none" is what turns it off (checked against
        # Ollama 0.18; "low" and think=false do not).
        ("ollama", True, True, None, False),
        ("ollama", True, False, "none", False),
        ("ollama", False, False, None, False),
    ],
)
async def test_reasoning_knobs_per_provider(
    client,
    account_with,
    fake_llm,
    preset,
    supports_reasoning,
    thinking,
    expected_effort,
    no_think,
):
    acct = await account_with(preset=preset, supports_reasoning=supports_reasoning)
    await client.post(
        "/chat/completions",
        json={"prompt": "q", "model": "fake-model", "thinking_mode": thinking},
        headers=acct.headers,
    )
    sent = fake_llm.requests[-1]
    assert sent.get("reasoning_effort") == expected_effort
    has_no_think = sent["messages"][0] == {"role": "system", "content": "/no_think"}
    assert has_no_think is no_think


async def test_thinking_content_only_when_requested(client, account_with, fake_llm):
    acct = await account_with(supports_reasoning=True)
    fake_llm.reply("4", reasoning="2+2=4").reply("4", reasoning="2+2=4")

    async def ask(thinking):
        return (
            await client.post(
                "/chat/completions",
                json={
                    "prompt": "2+2",
                    "model": "fake-model",
                    "thinking_mode": thinking,
                },
                headers=acct.headers,
            )
        ).json()

    assert (await ask(True))["thinking_content"] == "2+2=4"
    assert (await ask(False))["thinking_content"] is None


async def test_legacy_alias_still_works_end_to_end(
    client, make_account, fake_llm, monkeypatch
):
    """Old clients sending model="gemini" reach the env-seeded Gemini model."""
    monkeypatch.setattr(settings, "google_api_key", "AIza-test-key-000000000")
    acct = await make_account()
    fake_llm.reply("hola", usage=(1_000_000, 0))

    body = (
        await client.post(
            "/chat/completions",
            json={"prompt": "hi", "model": "gemini"},
            headers=acct.headers,
        )
    ).json()

    assert body["response"] == "hola"
    assert body["model_used"] == f"Google Gemini/{settings.gemini_model}"
    assert body["cost_usd"] == pytest.approx(0.50)
    assert fake_llm.configs[-1].api_key == "AIza-test-key-000000000"


async def test_undecryptable_provider_key_is_a_clear_error(
    client, account_with, fake_llm, db_session
):
    from sqlalchemy import select

    from llmwatch.db.models import Provider

    acct = await account_with()
    provider = (await db_session.execute(select(Provider))).scalar_one()
    provider.api_key_encrypted = "not-a-fernet-token"
    await db_session.commit()

    resp = await client.post(
        "/chat/completions",
        json={"prompt": "hi", "model": "fake-model"},
        headers=acct.headers,
    )
    assert resp.status_code == 502
    assert resp.json()["error_type"] == "decryption"
    assert fake_llm.requests == []


# ── Streaming ───────────────────────────────────────────────


def _events(text: str) -> list[dict]:
    return [
        json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")
    ]


async def _stream(client, account, **body):
    payload = {"prompt": "hello", "model": "fake-model", **body}
    return await client.post("/chat/stream", json=payload, headers=account.headers)


async def test_stream_event_sequence(client, account_with, fake_llm):
    acct = await account_with()
    fake_llm.reply("Hello streaming world", usage=(10, 4))

    resp = await _stream(client, acct)

    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/event-stream")
    assert resp.headers["x-accel-buffering"] == "no"
    events = _events(resp.text)
    types = [e["type"] for e in events]
    assert types[0] == "start"
    assert types[-2:] == ["usage", "done"]
    assert set(types[1:-2]) == {"delta"}
    assert "".join(e["text"] for e in events if e["type"] == "delta") == (
        "Hello streaming world"
    )
    assert events[0]["model_used"] == "Fake/fake-model"
    assert events[-2]["input_tokens"] == 10
    done = events[-1]
    assert done["cost_usd"] == pytest.approx(10 / 1e6 + 4 * 2 / 1e6)
    assert done["priced"] is True
    assert done["finish_reason"] == "stop"


async def test_stream_is_logged_with_usage(client, account_with, fake_llm):
    acct = await account_with()
    fake_llm.reply("Hello streaming world", usage=(10, 4))
    await _stream(client, acct)

    (log,) = await _logs(client, acct)
    assert log["success"] is True
    assert log["response_preview"] == "Hello streaming world"
    assert log["input_tokens"] == 10
    assert log["output_tokens"] == 4


async def test_stream_reasoning_events_only_when_thinking(
    client, account_with, fake_llm
):
    acct = await account_with(supports_reasoning=True)
    fake_llm.reply("4", reasoning="two plus two").reply("4", reasoning="two plus two")

    with_thinking = _events((await _stream(client, acct, thinking_mode=True)).text)
    without = _events((await _stream(client, acct, thinking_mode=False)).text)

    assert "".join(e["text"] for e in with_thinking if e["type"] == "reasoning") == (
        "two plus two"
    )
    assert not [e for e in without if e["type"] == "reasoning"]


async def test_stream_failure_before_first_byte_is_a_real_http_error(
    client, account_with, fake_llm
):
    acct = await account_with()
    fake_llm.fail(429, message="slow down", retry_after="3")

    resp = await _stream(client, acct)

    assert resp.status_code == 429
    assert resp.headers["retry-after"] == "3"
    assert resp.json()["error_type"] == "rate_limit"
    (log,) = await _logs(client, acct)
    assert log["success"] is False
    assert log["error_type"] == "rate_limit"


async def test_stream_failure_midway_sends_an_error_event_and_logs(
    client, account_with, fake_llm
):
    acct = await account_with()

    def broken_stream(request):
        async def body():
            chunk = {
                "id": "x",
                "object": "chat.completion.chunk",
                "created": 0,
                "model": "fake-model",
                "choices": [
                    {
                        "index": 0,
                        "delta": {"content": "partial "},
                        "finish_reason": None,
                    }
                ],
            }
            yield f"data: {json.dumps(chunk)}\n\n".encode()
            raise httpx.ReadError("connection reset")

        return httpx.Response(
            200, headers={"content-type": "text/event-stream"}, content=body()
        )

    fake_llm._handle = broken_stream  # type: ignore[method-assign]
    resp = await _stream(client, acct)

    events = _events(resp.text)
    assert events[-1]["type"] == "error"
    assert events[-1]["error_type"] == "connection"
    (log,) = await _logs(client, acct)
    assert log["success"] is False
    assert log["error_type"] == "connection"
    assert log["response_preview"] == "partial "


async def test_client_disconnect_stops_the_stream_and_is_logged(
    client, account_with, fake_llm
):
    from starlette.requests import Request

    acct = await account_with()
    fake_llm.reply("a long answer that keeps going and going", usage=(5, 50))

    async def disconnected(self):
        return True

    with patch.object(Request, "is_disconnected", disconnected):
        resp = await _stream(client, acct)

    events = _events(resp.text)
    assert "done" not in [e["type"] for e in events]
    deltas = [e for e in events if e["type"] == "delta"]
    assert len(deltas) <= 1  # stopped after the first chunk
    (log,) = await _logs(client, acct)
    assert log["success"] is False
    assert log["error_type"] == "cancelled"


async def test_stream_unknown_model_is_400(client, account_with, fake_llm):
    acct = await account_with()
    resp = await _stream(client, acct, model="nope")
    assert resp.status_code == 400
    assert fake_llm.requests == []
