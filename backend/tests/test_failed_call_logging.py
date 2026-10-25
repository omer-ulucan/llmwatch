"""
Regression tests: failed LLM calls are logged, so the error rate is real.

WHY: The chat route only logged after a successful call. A provider error raised
straight out of the handler, nothing was recorded, and the dashboard's error rate
was always 0%. Every failure also surfaced as a generic 500.
"""

from unittest.mock import patch

import httpx
import pytest

from llmwatch.services.llm_service import LegacyRoute, LLMService
from tests.fake_llm import FakeProvider


@pytest.fixture
def fake_gemini():
    fake = FakeProvider()
    with patch.object(LLMService, "__init__", lambda self: None):
        svc = LLMService()
    svc.routes = {
        "gemini": LegacyRoute(
            alias="gemini",
            client=fake.client(),
            model_id="gemini-test",
            preset="gemini",
        )
    }
    with (
        patch("llmwatch.routers.chat.get_llm_service", return_value=svc),
        patch("llmwatch.routers.chat.get_mlflow_service"),
    ):
        yield fake


async def _chat(client, account):
    return await client.post(
        "/chat/completions",
        json={"prompt": "hello there", "model": "gemini"},
        headers=account.headers,
    )


async def _logs(client, account):
    return (await client.get("/analytics/logs", headers=account.headers)).json()


@pytest.mark.parametrize(
    "status,kind,http_status",
    [
        (500, "server", 502),
        (503, "server", 502),
        (429, "rate_limit", 429),
        (401, "auth", 502),
        (400, "bad_request", 400),
        (404, "not_found", 400),
    ],
)
async def test_provider_errors_are_logged_and_mapped(
    client, make_account, fake_gemini, status, kind, http_status
):
    acct = await make_account()
    fake_gemini.fail(status, message="upstream says no")

    resp = await _chat(client, acct)

    assert resp.status_code == http_status
    body = resp.json()
    assert body["code"] == "LLM_SERVICE_ERROR"
    assert body["error_type"] == kind
    (log,) = await _logs(client, acct)
    assert log["success"] is False
    assert log["error_type"] == kind
    assert log["status_code"] == status
    assert "upstream says no" in log["error_message"]
    assert log["prompt_preview"] == "hello there"
    assert log["latency_ms"] >= 0
    assert log["cost_usd"] == 0


async def test_timeouts_are_logged_as_504(client, make_account, fake_gemini):
    acct = await make_account()
    fake_gemini.raise_(httpx.ReadTimeout("slow"))

    resp = await _chat(client, acct)

    assert resp.status_code == 504
    (log,) = await _logs(client, acct)
    assert log["error_type"] == "timeout"
    assert log["status_code"] is None


async def test_rate_limit_passes_retry_after_through(client, make_account, fake_gemini):
    acct = await make_account()
    fake_gemini.fail(429, retry_after="7")
    resp = await _chat(client, acct)
    assert resp.status_code == 429
    assert resp.headers["retry-after"] == "7"


async def test_error_rate_reflects_failures(client, make_account, fake_gemini):
    acct = await make_account()
    fake_gemini.reply("fine").fail(500).reply("fine").fail(503)
    for _ in range(4):
        await _chat(client, acct)

    summary = (await client.get("/analytics/summary", headers=acct.headers)).json()
    assert summary["total_requests"] == 4
    assert summary["error_rate_pct"] == 50.0


async def test_unconfigured_model_is_400_and_not_logged(client, make_account):
    """No provider call happened, so there is nothing to log."""
    acct = await make_account()
    with patch.object(LLMService, "__init__", lambda self: None):
        svc = LLMService()
    svc.routes = {}
    with patch("llmwatch.routers.chat.get_llm_service", return_value=svc):
        resp = await _chat(client, acct)
    assert resp.status_code == 400
    assert "Unsupported model" in resp.json()["error"]
    assert await _logs(client, acct) == []


async def test_error_messages_are_truncated(client, make_account, fake_gemini):
    acct = await make_account()
    fake_gemini.fail(500, message="x" * 5000)
    await _chat(client, acct)
    (log,) = await _logs(client, acct)
    assert len(log["error_message"]) <= 1000
