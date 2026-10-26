"""
Regression tests: LLM call logs and agent traces are actually persisted.

WHY: Logs and traces went to DynamoDB through boto3, which raises
"TypeError: Float types are not supported" for float latency/cost. The error was
caught and logged inside a background thread, so nothing was ever stored and the
dashboard and trace list were always empty. These tests go through the HTTP API:
make a call, then read it back through analytics / traces.
"""

import json
import logging

import pytest

LATENCY_MS = 812.4375
COST_USD = 0.000123456


# 12 input tokens at $1/1M + 9 output tokens at $2/1M
CHAT_COST_USD = 12 * 1.0 / 1_000_000 + 9 * 2.0 / 1_000_000


@pytest.fixture
def chat_account(make_account, add_model, fake_llm):
    """An account with a priced model; every reply reports 12 + 9 tokens."""
    for _ in range(10):
        fake_llm.reply("Paris is the capital of France.", usage=(12, 9))

    async def _new(**kwargs):
        account = await make_account(**kwargs)
        await add_model(account, input_price=1.0, output_price=2.0)
        return account

    return _new


async def _chat(client, account, prompt="What is the capital of France?"):
    resp = await client.post(
        "/chat/completions",
        json={"prompt": prompt, "model": "fake-model"},
        headers=account.headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── Chat logs ───────────────────────────────────────────────


async def test_chat_call_is_persisted_with_float_metrics(client, chat_account):
    acct = await chat_account()
    reply = await _chat(client, acct)

    summary = (await client.get("/analytics/summary", headers=acct.headers)).json()
    assert summary["total_requests"] == 1
    assert summary["total_cost_usd"] == pytest.approx(CHAT_COST_USD)

    (log,) = (await client.get("/analytics/logs", headers=acct.headers)).json()["items"]
    assert isinstance(log["latency_ms"], float)
    assert log["latency_ms"] == pytest.approx(reply["latency_ms"])
    assert log["cost_usd"] == pytest.approx(CHAT_COST_USD)
    assert log["input_tokens"] == 12
    assert log["output_tokens"] == 9
    assert log["model_name"] == "fake-model"
    assert log["provider_name"] == "Fake"
    assert log["success"] is True
    assert log["prompt_preview"] == "What is the capital of France?"
    assert log["response_preview"] == "Paris is the capital of France."


async def test_logs_are_isolated_per_workspace(client, chat_account):
    alice = await chat_account(workspace="A")
    bob = await chat_account(workspace="B")
    await _chat(client, alice)

    assert (await client.get("/analytics/logs", headers=bob.headers)).json()[
        "items"
    ] == []
    summary = (await client.get("/analytics/summary", headers=bob.headers)).json()
    assert summary["total_requests"] == 0


async def test_timeseries_reads_persisted_logs(client, chat_account):
    acct = await chat_account()
    await _chat(client, acct)
    await _chat(client, acct)

    series = (await client.get("/analytics/timeseries", headers=acct.headers)).json()
    assert sum(series["request_counts"]) == 2
    assert sum(series["costs"]) == pytest.approx(2 * CHAT_COST_USD)


async def test_long_previews_are_truncated(client, chat_account):
    acct = await chat_account()
    await _chat(client, acct, prompt="x" * 5000)
    (log,) = (await client.get("/analytics/logs", headers=acct.headers)).json()["items"]
    assert len(log["prompt_preview"]) == 200


async def test_log_storage_failure_is_logged_not_silent(
    client, chat_account, monkeypatch, caplog
):
    from llmwatch.db.models import LLMLog

    acct = await chat_account()

    def explode(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(LLMLog, "__init__", explode)
    with caplog.at_level(logging.ERROR, logger="llmwatch"):
        await _chat(client, acct)  # logging must not break the request

    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "Failed to store LLM call log" in messages
    assert acct.workspace_id in messages


# ── Agent traces ────────────────────────────────────────────


async def _run_agent(client, account):
    resp = await client.post(
        "/agent/run",
        json={"prompt": "meaning of life?", "model": "fake-model", "tools": []},
        headers=account.headers,
    )
    assert resp.status_code == 200
    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[-1]["event_type"] == "run_end"
    return events[0]["run_id"]


async def test_agent_run_is_persisted_and_listed(client, chat_account):
    acct = await chat_account()
    run_id = await _run_agent(client, acct)

    (trace,) = (await client.get("/agent/traces", headers=acct.headers)).json()[
        "traces"
    ]
    assert trace["run_id"] == run_id
    assert trace["prompt"] == "meaning of life?"
    assert trace["model_used"] == "Fake/fake-model"
    assert isinstance(trace["total_latency_ms"], float)
    assert trace["total_cost_usd"] == pytest.approx(CHAT_COST_USD)
    assert trace["success"] is True
    assert "steps" not in trace  # list view stays light

    detail = (await client.get(f"/agent/traces/{run_id}", headers=acct.headers)).json()
    assert detail["trace"]["run_id"] == run_id
    assert detail["trace"]["final_answer"] == "Paris is the capital of France."
    assert detail["trace"]["steps"]


async def test_agent_analytics_reads_persisted_traces(client, chat_account):
    acct = await chat_account()
    await _run_agent(client, acct)
    await _run_agent(client, acct)

    stats = (await client.get("/agent/analytics", headers=acct.headers)).json()
    assert stats["total_runs"] == 2
    assert stats["success_rate"] == 100.0
    assert stats["total_cost_usd"] == pytest.approx(2 * CHAT_COST_USD)


async def test_traces_are_isolated_per_workspace(client, chat_account):
    alice = await chat_account(workspace="A")
    bob = await chat_account(workspace="B")
    run_id = await _run_agent(client, alice)

    assert (await client.get("/agent/traces", headers=bob.headers)).json() == {
        "traces": []
    }
    resp = await client.get(f"/agent/traces/{run_id}", headers=bob.headers)
    assert resp.status_code == 404
