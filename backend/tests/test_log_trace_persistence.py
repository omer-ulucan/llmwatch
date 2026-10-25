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
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from llmwatch.services.tracing_service import AgentEvent, AgentRunSummary

LATENCY_MS = 812.4375
COST_USD = 0.000123456


def _llm_result(**overrides):
    return {
        "response": "Paris is the capital of France.",
        "thinking_content": None,
        "latency_ms": LATENCY_MS,
        "input_tokens": 12,
        "output_tokens": 9,
        "cost_usd": COST_USD,
        "model_used": "gemini",
        "thinking_mode": False,
        **overrides,
    }


@pytest.fixture
def fake_llm():
    llm = MagicMock()
    llm.execute_chat = AsyncMock(return_value=_llm_result())
    with (
        patch("llmwatch.routers.chat.get_llm_service", return_value=llm),
        patch("llmwatch.routers.chat.get_mlflow_service"),
    ):
        yield llm


async def _chat(client, account, prompt="What is the capital of France?"):
    return await client.post(
        "/chat/completions",
        json={"prompt": prompt, "model": "gemini"},
        headers=account.headers,
    )


# ── Chat logs ───────────────────────────────────────────────


async def test_chat_call_is_persisted_with_float_metrics(
    client, make_account, fake_llm
):
    acct = await make_account()
    assert (await _chat(client, acct)).status_code == 200

    summary = (await client.get("/analytics/summary", headers=acct.headers)).json()
    assert summary["total_requests"] == 1
    assert summary["total_cost_usd"] == pytest.approx(COST_USD)
    assert summary["avg_latency_ms"] == pytest.approx(LATENCY_MS, abs=0.01)

    (log,) = (await client.get("/analytics/logs", headers=acct.headers)).json()
    assert log["latency_ms"] == pytest.approx(LATENCY_MS)
    assert log["cost_usd"] == pytest.approx(COST_USD)
    assert log["input_tokens"] == 12
    assert log["output_tokens"] == 9
    assert log["model_name"] == "gemini"
    assert log["success"] is True
    assert log["prompt_preview"] == "What is the capital of France?"
    assert log["response_preview"] == "Paris is the capital of France."


async def test_logs_are_isolated_per_workspace(client, make_account, fake_llm):
    alice = await make_account(workspace="A")
    bob = await make_account(workspace="B")
    await _chat(client, alice)

    assert (await client.get("/analytics/logs", headers=bob.headers)).json() == []
    summary = (await client.get("/analytics/summary", headers=bob.headers)).json()
    assert summary["total_requests"] == 0


async def test_timeseries_reads_persisted_logs(client, make_account, fake_llm):
    acct = await make_account()
    await _chat(client, acct)
    await _chat(client, acct)

    series = (await client.get("/analytics/timeseries", headers=acct.headers)).json()
    assert len(series["timestamps"]) == 2
    assert series["costs"] == [pytest.approx(COST_USD)] * 2


async def test_long_previews_are_truncated(client, make_account, fake_llm):
    acct = await make_account()
    await _chat(client, acct, prompt="x" * 5000)
    (log,) = (await client.get("/analytics/logs", headers=acct.headers)).json()
    assert len(log["prompt_preview"]) == 200


async def test_log_storage_failure_is_logged_not_silent(
    client, make_account, fake_llm, monkeypatch, caplog
):
    from llmwatch.db.models import LLMLog

    acct = await make_account()

    def explode(*args, **kwargs):
        raise RuntimeError("disk full")

    monkeypatch.setattr(LLMLog, "__init__", explode)
    with caplog.at_level(logging.ERROR, logger="llmwatch"):
        resp = await _chat(client, acct)

    assert resp.status_code == 200  # logging must not break the request
    messages = " ".join(r.getMessage() for r in caplog.records)
    assert "Failed to store LLM call log" in messages
    assert acct.workspace_id in messages


# ── Agent traces ────────────────────────────────────────────


def _fake_agent(run_id="run-1"):
    async def run_agent(**kwargs):
        yield AgentEvent(
            run_id=run_id, step_index=0, event_type="run_start", content="go"
        )
        yield AgentEvent(
            run_id=run_id,
            step_index=1,
            event_type="final_answer",
            content="42",
            latency_ms=LATENCY_MS,
        )
        summary = AgentRunSummary(
            run_id=run_id,
            total_steps=2,
            total_latency_ms=LATENCY_MS,
            total_tokens=21,
            total_cost_usd=COST_USD,
            tools_used=["web_search"],
            model_used="gemini",
            success=True,
        )
        yield AgentEvent(
            run_id=run_id,
            step_index=2,
            event_type="run_end",
            content=summary.model_dump_json(),
        )

    agent = MagicMock()
    agent.run_agent = run_agent
    return agent


async def _run_agent(client, account, run_id="run-1"):
    with (
        patch(
            "llmwatch.routers.agent.get_agent_service", return_value=_fake_agent(run_id)
        ),
        patch("llmwatch.routers.agent.get_mlflow_service"),
    ):
        resp = await client.post(
            "/agent/run",
            json={
                "prompt": "meaning of life?",
                "model": "gemini",
                "tools": ["web_search"],
            },
            headers=account.headers,
        )
    assert resp.status_code == 200
    events = [
        json.loads(line[6:])
        for line in resp.text.splitlines()
        if line.startswith("data: ")
    ]
    assert events[-1]["event_type"] == "run_end"
    return events


async def test_agent_run_is_persisted_and_listed(client, make_account):
    acct = await make_account()
    await _run_agent(client, acct)

    traces = (await client.get("/agent/traces", headers=acct.headers)).json()["traces"]
    (trace,) = traces
    assert trace["run_id"] == "run-1"
    assert trace["prompt"] == "meaning of life?"
    assert trace["model_used"] == "gemini"
    assert trace["tools_used"] == ["web_search"]
    assert trace["total_latency_ms"] == pytest.approx(LATENCY_MS)
    assert trace["total_cost_usd"] == pytest.approx(COST_USD)
    assert trace["success"] is True
    assert "steps" not in trace  # list view stays light

    detail = (await client.get("/agent/traces/run-1", headers=acct.headers)).json()
    assert detail["trace"]["run_id"] == "run-1"
    assert "steps" in detail["trace"]


async def test_agent_analytics_reads_persisted_traces(client, make_account):
    acct = await make_account()
    await _run_agent(client, acct, "run-1")
    await _run_agent(client, acct, "run-2")

    stats = (await client.get("/agent/analytics", headers=acct.headers)).json()
    assert stats["total_runs"] == 2
    assert stats["success_rate"] == 100.0
    assert stats["total_cost_usd"] == pytest.approx(2 * COST_USD)
    assert stats["tool_usage"] == {"web_search": 2}


async def test_traces_are_isolated_per_workspace(client, make_account):
    alice = await make_account(workspace="A")
    bob = await make_account(workspace="B")
    await _run_agent(client, alice)

    assert (await client.get("/agent/traces", headers=bob.headers)).json() == {
        "traces": []
    }
    resp = await client.get("/agent/traces/run-1", headers=bob.headers)
    assert resp.status_code == 404
