"""
Tests for the native agent tools (no network: search, fetch and DNS are faked).
"""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from llmwatch.agent import tools
from llmwatch.agent.tools import ToolContext, build_toolset, run_tool
from llmwatch.config import settings
from llmwatch.db.models import LLMLog
from llmwatch.security.ssrf import FetchResult

CTX = ToolContext(workspace_id="ws-1")


# ── Specs and the toolset ───────────────────────────────────


def test_every_tool_has_a_valid_openai_spec():
    for tool in tools.ALL_TOOLS.values():
        spec = tool.spec()
        assert spec["type"] == "function"
        fn = spec["function"]
        assert fn["name"] == tool.name
        assert fn["description"]
        assert fn["parameters"]["type"] == "object"
        assert fn["parameters"]["additionalProperties"] is False
        for required in fn["parameters"]["required"]:
            assert required in fn["parameters"]["properties"]
        json.dumps(spec)  # serialisable


def test_python_is_not_built_unless_enabled(monkeypatch):
    monkeypatch.setattr(settings, "enable_code_execution", False)
    assert "python" not in build_toolset(["web_search", "python"])
    assert "python" not in tools.available_tool_names()
    monkeypatch.setattr(settings, "enable_code_execution", True)
    assert "python" in build_toolset(["python"])


def test_old_tool_names_are_aliases(monkeypatch):
    monkeypatch.setattr(settings, "enable_code_execution", True)
    toolset = build_toolset(["code_execute", "db_query", "doc_analyze", "web_search"])
    assert set(toolset) == {"python", "query_usage", "fetch_url", "web_search"}


def test_unknown_tools_are_dropped():
    assert build_toolset(["web_search", "rm_rf"]) == {"web_search": tools.WEB_SEARCH}


# ── run_tool: argument handling ─────────────────────────────


async def test_invalid_json_arguments_are_an_error_result():
    result = await run_tool(tools.FETCH_URL, "{not json", CTX)
    assert result.is_error
    assert "valid JSON" in result.content


async def test_non_object_arguments_are_an_error_result():
    result = await run_tool(tools.FETCH_URL, '["x"]', CTX)
    assert result.is_error


async def test_missing_required_argument_is_an_error_result():
    result = await run_tool(tools.FETCH_URL, "{}", CTX)
    assert result.is_error
    assert "url" in result.content


async def test_tool_exceptions_become_error_results(monkeypatch):
    def boom(query, max_results):
        raise RuntimeError("search backend down")

    monkeypatch.setattr(tools, "_ddgs_text", boom)
    result = await run_tool(tools.WEB_SEARCH, '{"query": "x"}', CTX)
    assert result.is_error
    assert "search backend down" in result.content


async def test_slow_tools_time_out(monkeypatch):
    import asyncio

    async def slow(args, ctx):
        await asyncio.sleep(5)

    tool = tools.Tool("slow", "slow", {"type": "object", "properties": {}}, slow)
    result = await run_tool(tool, "{}", CTX, timeout=0.05)
    assert result.is_error
    assert "timed out" in result.content


# ── web_search ──────────────────────────────────────────────


async def test_web_search_formats_results(monkeypatch):
    calls = []

    def fake(query, max_results):
        calls.append((query, max_results))
        return [
            {
                "title": "LLMWatch",
                "body": "Self-hosted LLMOps",
                "href": "https://x.dev",
            },
            {"title": "Other", "body": "Snippet", "href": "https://y.dev"},
        ]

    monkeypatch.setattr(tools, "_ddgs_text", fake)
    result = await run_tool(
        tools.WEB_SEARCH, '{"query": "llmwatch", "max_results": 50}', CTX
    )

    assert not result.is_error
    assert "1. LLMWatch" in result.content
    assert "URL: https://y.dev" in result.content
    assert calls == [("llmwatch", 10)]  # capped


async def test_web_search_no_results(monkeypatch):
    monkeypatch.setattr(tools, "_ddgs_text", lambda q, n: [])
    result = await run_tool(tools.WEB_SEARCH, '{"query": "zzzz"}', CTX)
    assert result.content == "No results found for: zzzz"


# ── fetch_url ───────────────────────────────────────────────


def _fetched(text: str, content_type="text/html", status=200, url="https://ex.com"):
    return FetchResult(
        url=url,
        status_code=status,
        headers=httpx.Headers({"content-type": content_type}),
        content=text.encode(),
    )


async def test_fetch_url_extracts_text(monkeypatch):
    async def fake_fetch(url, **kwargs):
        return _fetched("<html><script>evil()</script><p>Hello <b>World</b></p></html>")

    monkeypatch.setattr("llmwatch.security.ssrf.safe_fetch", fake_fetch)
    result = await run_tool(tools.FETCH_URL, '{"url": "https://ex.com"}', CTX)
    assert not result.is_error
    assert "Hello World" in result.content
    assert "evil" not in result.content


async def test_fetch_url_blocks_internal_addresses_for_real():
    """No fake here: the SSRF guard itself refuses the metadata address."""
    result = await run_tool(
        tools.FETCH_URL, '{"url": "http://169.254.169.254/latest/meta-data/"}', CTX
    )
    assert result.is_error
    assert result.content.startswith("Request blocked:")


async def test_fetch_url_rejects_non_http_schemes():
    result = await run_tool(tools.FETCH_URL, '{"url": "file:///etc/passwd"}', CTX)
    assert result.is_error


async def test_fetch_url_http_errors(monkeypatch):
    async def fake_fetch(url, **kwargs):
        return _fetched("nope", status=404)

    monkeypatch.setattr("llmwatch.security.ssrf.safe_fetch", fake_fetch)
    result = await run_tool(tools.FETCH_URL, '{"url": "https://ex.com/x"}', CTX)
    assert result.is_error
    assert "404" in result.content


async def test_fetch_url_output_is_truncated(monkeypatch):
    async def fake_fetch(url, **kwargs):
        return _fetched("a" * 50_000, content_type="text/plain")

    monkeypatch.setattr("llmwatch.security.ssrf.safe_fetch", fake_fetch)
    result = await run_tool(tools.FETCH_URL, '{"url": "https://ex.com"}', CTX)
    assert len(result.content) < 9000
    assert "[truncated:" in result.content


# ── query_usage ─────────────────────────────────────────────


async def _seed(db_session, workspace_id, n, cost, model="gpt-x", ago_hours=1):
    for i in range(n):
        db_session.add(
            LLMLog(
                workspace_id=workspace_id,
                created_at=datetime.now(UTC) - timedelta(hours=ago_hours, minutes=i),
                model_name=model,
                provider_name="OpenAI",
                cost_usd=cost,
                latency_ms=100.0,
            )
        )
    await db_session.commit()


async def test_query_usage_summarises_the_callers_workspace(make_account, db_session):
    mine = await make_account()
    theirs = await make_account(workspace="Other")
    await _seed(db_session, mine.workspace_id, 3, 0.01)
    await _seed(db_session, theirs.workspace_id, 50, 9.0)

    result = await run_tool(
        tools.QUERY_USAGE, '{"hours": 24}', ToolContext(mine.workspace_id)
    )
    data = json.loads(result.content)

    assert data["requests"] == 3
    assert data["cost_usd"] == pytest.approx(0.03)
    assert set(data["by_model"]) == {"OpenAI/gpt-x"}


async def test_query_usage_window_and_model_filter(make_account, db_session):
    acct = await make_account()
    await _seed(db_session, acct.workspace_id, 2, 0.01, model="gpt-x", ago_hours=1)
    await _seed(db_session, acct.workspace_id, 4, 0.01, model="llama", ago_hours=30)
    ctx = ToolContext(acct.workspace_id)

    day = json.loads((await run_tool(tools.QUERY_USAGE, '{"hours": 24}', ctx)).content)
    week = json.loads(
        (await run_tool(tools.QUERY_USAGE, '{"hours": 168}', ctx)).content
    )
    llama = json.loads(
        (
            await run_tool(tools.QUERY_USAGE, '{"hours": 168, "model": "llama"}', ctx)
        ).content
    )
    assert day["requests"] == 2
    assert week["requests"] == 6
    assert llama["requests"] == 4


async def test_query_usage_ignores_a_workspace_argument(make_account, db_session):
    """The model can't widen the scope: unknown args are not used for scoping."""
    mine = await make_account()
    theirs = await make_account(workspace="Other")
    await _seed(db_session, theirs.workspace_id, 5, 1.0)
    result = await run_tool(
        tools.QUERY_USAGE,
        json.dumps({"workspace_id": theirs.workspace_id}),
        ToolContext(mine.workspace_id),
    )
    assert json.loads(result.content)["requests"] == 0


async def test_query_usage_bad_hours(make_account):
    acct = await make_account()
    result = await run_tool(
        tools.QUERY_USAGE, '{"hours": "soon"}', ToolContext(acct.workspace_id)
    )
    assert result.is_error


# ── python ──────────────────────────────────────────────────


async def test_python_runs_when_enabled(monkeypatch):
    monkeypatch.setattr(settings, "enable_code_execution", True)
    result = await run_tool(tools.PYTHON, json.dumps({"code": "print(6*7)"}), CTX)
    assert not result.is_error
    assert result.content.strip() == "42"


async def test_python_errors_are_flagged(monkeypatch):
    monkeypatch.setattr(settings, "enable_code_execution", True)
    result = await run_tool(tools.PYTHON, json.dumps({"code": "1/0"}), CTX)
    assert result.is_error
    assert "ZeroDivisionError" in result.content


async def test_python_refuses_when_disabled_even_if_called_directly(monkeypatch):
    monkeypatch.setattr(settings, "enable_code_execution", False)
    result = await run_tool(tools.PYTHON, json.dumps({"code": "print(1)"}), CTX)
    assert result.is_error
    assert "disabled" in result.content
