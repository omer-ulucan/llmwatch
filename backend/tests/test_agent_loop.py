"""
Tests for the native agent loop and /agent endpoints, against a scripted fake model.

Regressions covered: traces were saved with empty steps and final answer, agent cost
was always $0, and the LangChain executor pushed events into an asyncio.Queue from a
worker thread (gone: everything here runs on the event loop).
"""

import asyncio
import json

import pytest
from sqlalchemy import select

from llmwatch.agent import tools as agent_tools
from llmwatch.agent.loop import AgentRequest, AgentRun, registry
from llmwatch.config import settings
from llmwatch.db.models import AgentTrace, LLMLog
from llmwatch.providers.models import resolve_model


@pytest.fixture
def search_results(monkeypatch):
    calls = []

    def fake(query, max_results):
        calls.append(query)
        return [{"title": "Paris", "body": "Capital of France", "href": "https://p.fr"}]

    monkeypatch.setattr(agent_tools, "_ddgs_text", fake)
    return calls


@pytest.fixture
def agent_account(make_account, add_model):
    async def _new(**model_kwargs):
        account = await make_account()
        # $1 / 1M input, $2 / 1M output
        await add_model(account, **model_kwargs)
        return account

    return _new


def _events(text: str) -> list[dict]:
    return [
        json.loads(line[6:]) for line in text.splitlines() if line.startswith("data: ")
    ]


async def _run(client, account, **body):
    payload = {
        "prompt": "What is the capital of France?",
        "model": "fake-model",
        "tools": ["web_search"],
        **body,
    }
    resp = await client.post("/agent/run", json=payload, headers=account.headers)
    assert resp.status_code == 200, resp.text
    return resp, _events(resp.text)


# ── A full run ──────────────────────────────────────────────


async def test_tool_using_run_streams_the_event_contract(
    client, agent_account, fake_llm, search_results
):
    acct = await agent_account()
    fake_llm.call_tool("web_search", {"query": "capital of France"}, usage=(100, 20))
    fake_llm.reply("The capital of France is Paris.", usage=(300, 40))

    resp, events = await _run(client, acct)

    assert [e["event_type"] for e in events] == [
        "run_start",
        "thinking",
        "tool_call",
        "tool_result",
        "final_answer",
        "run_end",
    ]
    assert resp.headers["x-run-id"] == events[0]["run_id"]
    assert {e["run_id"] for e in events} == {events[0]["run_id"]}
    assert [e["step_index"] for e in events] == list(range(6))

    tool_call = events[2]
    assert tool_call["tool_name"] == "web_search"
    assert json.loads(tool_call["tool_input"]) == {"query": "capital of France"}
    assert "Capital of France" in events[3]["content"]
    assert events[3]["is_error"] is False
    assert events[3]["latency_ms"] >= 0
    assert search_results == ["capital of France"]

    # Per-step model metrics
    thinking, final = events[1], events[4]
    assert thinking["tokens"] == 120
    assert thinking["cost_usd"] == pytest.approx(100 / 1e6 + 20 * 2 / 1e6)
    assert final["content"] == "The capital of France is Paris."
    assert final["tokens"] == 340


async def test_run_summary_sums_tokens_and_cost(
    client, agent_account, fake_llm, search_results
):
    """Regression: agent cost was always $0 (_total_cost was never incremented)."""
    acct = await agent_account()
    fake_llm.call_tool("web_search", {"query": "x"}, usage=(100, 20))
    fake_llm.reply("done", usage=(300, 40))

    _, events = await _run(client, acct)
    summary = json.loads(events[-1]["content"])

    assert summary["total_tokens"] == 460
    assert summary["total_cost_usd"] == pytest.approx(
        (100 + 300) / 1e6 + (20 + 40) * 2 / 1e6
    )
    assert summary["llm_calls"] == 2
    assert summary["tools_used"] == ["web_search"]
    assert summary["success"] is True
    assert summary["status"] == "success"
    assert summary["model_used"] == "Fake/fake-model"
    assert summary["priced"] is True


async def test_trace_is_stored_with_steps_and_final_answer(
    client, agent_account, fake_llm, search_results
):
    """Regression: traces were saved with steps=[] and final_answer=""."""
    acct = await agent_account()
    fake_llm.call_tool("web_search", {"query": "x"})
    fake_llm.reply("The capital of France is Paris.")

    _, events = await _run(client, acct)
    run_id = events[0]["run_id"]
    trace = (await client.get(f"/agent/traces/{run_id}", headers=acct.headers)).json()[
        "trace"
    ]

    assert trace["status"] == "success"
    assert trace["success"] is True
    assert trace["final_answer"] == "The capital of France is Paris."
    assert [s["event_type"] for s in trace["steps"]] == [
        e["event_type"] for e in events
    ]
    assert trace["tools_used"] == ["web_search"]
    assert trace["total_cost_usd"] > 0
    assert trace["model_used"] == "Fake/fake-model"


async def test_tool_results_go_back_to_the_model(
    client, agent_account, fake_llm, search_results
):
    acct = await agent_account()
    fake_llm.call_tool("web_search", {"query": "x"}, call_id="call_42")
    fake_llm.reply("done")

    await _run(client, acct)

    first, second = fake_llm.requests[-2], fake_llm.requests[-1]
    assert [t["function"]["name"] for t in first["tools"]] == ["web_search"]
    assert first["tool_choice"] == "auto"
    assistant, tool_msg = second["messages"][-2], second["messages"][-1]
    assert assistant["role"] == "assistant"
    assert assistant["tool_calls"][0]["id"] == "call_42"
    assert assistant["tool_calls"][0]["function"]["name"] == "web_search"
    assert tool_msg == {
        "role": "tool",
        "tool_call_id": "call_42",
        "content": tool_msg["content"],
    }
    assert "Capital of France" in tool_msg["content"]


async def test_each_model_call_is_logged_for_analytics(
    client, agent_account, fake_llm, search_results, db_session
):
    acct = await agent_account()
    fake_llm.call_tool("web_search", {"query": "x"}, usage=(10, 5))
    fake_llm.reply("done", usage=(20, 5))

    _, events = await _run(client, acct)

    logs = (await db_session.execute(select(LLMLog))).scalars().all()
    assert len(logs) == 2
    assert {log.source for log in logs} == {"agent"}
    assert {log.trace_id for log in logs} == {events[0]["run_id"]}
    assert sum(log.input_tokens for log in logs) == 30


async def test_direct_answer_without_tools(client, agent_account, fake_llm):
    acct = await agent_account()
    fake_llm.reply("Hello!", reasoning="Simple greeting")

    _, events = await _run(client, acct, prompt="hi", tools=[])

    assert [e["event_type"] for e in events] == [
        "run_start",
        "thinking",
        "final_answer",
        "run_end",
    ]
    assert events[1]["content"] == "Simple greeting"
    assert events[1]["tokens"] == 7  # metrics sit on the single model-call step
    assert "tokens" not in events[2]
    assert "tools" not in fake_llm.requests[-1]  # no tools => none offered


# ── Things going wrong ──────────────────────────────────────


async def test_unknown_tool_from_the_model_is_reported_back(
    client, agent_account, fake_llm
):
    acct = await agent_account()
    fake_llm.call_tool("rm_rf", {"path": "/"})
    fake_llm.reply("Sorry, I can't do that.")

    _, events = await _run(client, acct)

    result = next(e for e in events if e["event_type"] == "tool_result")
    assert result["is_error"] is True
    assert "unknown or disabled tool" in result["content"]
    assert events[-2]["event_type"] == "final_answer"


async def test_disabled_python_tool_is_not_offered_or_run(
    client, agent_account, fake_llm, monkeypatch
):
    monkeypatch.setattr(settings, "enable_code_execution", False)
    acct = await agent_account()
    resp = await client.post(
        "/agent/run",
        json={"prompt": "x", "model": "fake-model", "tools": ["python"]},
        headers=acct.headers,
    )
    assert resp.status_code == 422
    assert "disabled" in resp.text

    # Even if the model asks for it, it doesn't run.
    fake_llm.call_tool("python", {"code": "print(1)"})
    fake_llm.reply("ok")
    _, events = await _run(client, acct, tools=["web_search"])
    result = next(e for e in events if e["event_type"] == "tool_result")
    assert result["is_error"] is True


async def test_max_iterations_ends_the_run_with_an_error(
    client, agent_account, fake_llm, search_results
):
    acct = await agent_account()
    for i in range(3):
        fake_llm.call_tool("web_search", {"query": f"try {i}"}, call_id=f"c{i}")

    _, events = await _run(client, acct, max_iterations=2)

    error = events[-2]
    assert error["event_type"] == "error"
    assert error["error_type"] == "max_iterations"
    summary = json.loads(events[-1]["content"])
    assert summary["status"] == "error"
    trace = (
        await client.get(f"/agent/traces/{events[0]['run_id']}", headers=acct.headers)
    ).json()["trace"]
    assert trace["status"] == "error"
    assert "max_iterations" in trace["error"]


async def test_provider_error_ends_the_run_and_is_logged(
    client, agent_account, fake_llm, search_results, db_session
):
    acct = await agent_account()
    fake_llm.call_tool("web_search", {"query": "x"})
    fake_llm.fail(503, message="overloaded")

    _, events = await _run(client, acct)

    error = events[-2]
    assert error["event_type"] == "error"
    assert error["error_type"] == "server"
    assert "overloaded" in error["content"]
    assert json.loads(events[-1]["content"])["status"] == "error"
    failed = (
        await db_session.execute(select(LLMLog).where(LLMLog.success.is_(False)))
    ).scalar_one()
    assert failed.error_type == "server"


async def test_unknown_model_is_400_before_streaming(client, agent_account, fake_llm):
    acct = await agent_account()
    resp = await client.post(
        "/agent/run",
        json={"prompt": "x", "model": "nope", "tools": []},
        headers=acct.headers,
    )
    assert resp.status_code == 400
    assert fake_llm.requests == []


async def test_legacy_request_body_still_works(
    client, make_account, fake_llm, search_results, monkeypatch
):
    """Old clients: model "gemini" and the old tool names."""
    monkeypatch.setattr(settings, "google_api_key", "AIza-test-key-000000000")
    acct = await make_account()
    fake_llm.call_tool("web_search", {"query": "x"})
    fake_llm.reply("done")

    _, events = await _run(
        client, acct, model="gemini", tools=["web_search", "db_query", "doc_analyze"]
    )
    assert events[-2]["event_type"] == "final_answer"
    tools_offered = {t["function"]["name"] for t in fake_llm.requests[0]["tools"]}
    assert tools_offered == {"web_search", "query_usage", "fetch_url"}


# ── Cancellation ────────────────────────────────────────────


async def test_cancel_stops_a_run_even_mid_tool(
    make_account, add_model, fake_llm, monkeypatch, db_session
):
    acct = await make_account()
    await add_model(acct)
    started = asyncio.Event()

    async def slow_search(args, ctx):
        started.set()
        await asyncio.sleep(30)

    slow_tool = agent_tools.Tool(
        "web_search", "slow", agent_tools.WEB_SEARCH.parameters, slow_search
    )
    monkeypatch.setitem(agent_tools.ALL_TOOLS, "web_search", slow_tool)
    fake_llm.call_tool("web_search", {"query": "x"})

    resolved = await resolve_model(db_session, acct.workspace_id, "fake-model")
    run = AgentRun(
        AgentRequest(prompt="x", tools=["web_search"], workspace_id=acct.workspace_id),
        resolved,
        resolved.client(),
    )
    active = registry.register(run.run_id, acct.workspace_id)
    run.cancel = active.cancel

    events = []

    async def consume():
        async for event in run.events():
            events.append(event)

    task = asyncio.create_task(consume())
    await asyncio.wait_for(started.wait(), 5)
    assert registry.cancel(run.run_id, "some-other-workspace") is False
    assert registry.cancel(run.run_id, acct.workspace_id) is True
    await asyncio.wait_for(task, 5)  # returns promptly, not after 30s
    await run.save()
    registry.unregister(run.run_id)

    assert events[-2].event_type == "error"
    assert events[-2].error_type == "cancelled"
    assert run.status == "cancelled"
    db_session.expire_all()
    trace = await db_session.get(AgentTrace, run.run_id)
    assert trace.status == "cancelled"
    assert len(trace.steps) == len(events)


async def test_cancel_endpoint_unknown_run_is_404(client, agent_account):
    acct = await agent_account()
    resp = await client.post("/agent/runs/not-running/cancel", headers=acct.headers)
    assert resp.status_code == 404


async def test_client_disconnect_cancels_and_saves(
    client, agent_account, fake_llm, search_results, db_session
):
    from unittest.mock import patch

    from starlette.requests import Request

    acct = await agent_account()
    fake_llm.call_tool("web_search", {"query": "x"})
    fake_llm.reply("never reached")

    async def disconnected(self):
        return True

    with patch.object(Request, "is_disconnected", disconnected):
        _, events = await _run(client, acct)

    assert "final_answer" not in [e["event_type"] for e in events]
    trace = (await db_session.execute(select(AgentTrace))).scalar_one()
    assert trace.status == "cancelled"
    assert trace.steps  # what happened before the disconnect is kept


async def test_running_runs_are_visible_in_the_trace_list(
    make_account, add_model, fake_llm, db_session, client
):
    acct = await make_account()
    await add_model(acct)
    fake_llm.reply("done")
    resolved = await resolve_model(db_session, acct.workspace_id, "fake-model")
    run = AgentRun(
        AgentRequest(prompt="x", tools=[], workspace_id=acct.workspace_id),
        resolved,
        resolved.client(),
    )
    events = run.events()
    await anext(events)  # run_start
    await anext(events)  # model call done -> trace exists, status "running"
    listing = (await client.get("/agent/traces", headers=acct.headers)).json()
    assert listing["traces"][0]["status"] == "running"
    async for _ in events:
        pass
    await run.save()


# ── Analytics and tools endpoint ────────────────────────────


async def test_agent_analytics(client, agent_account, fake_llm, search_results):
    acct = await agent_account()
    fake_llm.call_tool("web_search", {"query": "x"}).reply("done")
    fake_llm.fail(500)
    await _run(client, acct)
    await _run(client, acct)

    stats = (await client.get("/agent/analytics", headers=acct.headers)).json()
    assert stats["total_runs"] == 2
    assert stats["success_rate"] == 50.0
    assert stats["tool_usage"] == {"web_search": 1}
    assert stats["model_breakdown"] == {"Fake/fake-model": 2}
    assert stats["total_cost_usd"] > 0


async def test_tools_endpoint_describes_tools(client, agent_account, monkeypatch):
    monkeypatch.setattr(settings, "enable_code_execution", False)
    acct = await agent_account()
    body = (await client.get("/agent/tools", headers=acct.headers)).json()
    assert body["tools"] == ["web_search", "fetch_url", "query_usage"]
    assert all(d["description"] for d in body["details"])
