"""
Tests for SQL analytics over real time windows.

Regressions covered: the `hours` parameter used to be ignored, aggregation only
looked at the newest 500/100 rows, and the model breakdown only knew "qwen" and
"gemini".
"""

import csv
import io
from datetime import UTC, datetime, timedelta

import pytest

from llmwatch.db.models import LLMLog
from llmwatch.exceptions import ValidationException
from llmwatch.services.analytics import Window, bucket_seconds, resolve_window

NOW = datetime.now(UTC)


def _log(workspace_id, *, ago=timedelta(minutes=5), **fields):
    defaults = dict(
        model_name="gpt-x",
        provider_name="OpenAI",
        latency_ms=100.0,
        cost_usd=0.01,
        input_tokens=10,
        output_tokens=5,
        success=True,
        prompt_preview="hello",
    )
    return LLMLog(
        workspace_id=workspace_id, created_at=NOW - ago, **{**defaults, **fields}
    )


@pytest.fixture
async def seeded(make_account, db_session):
    """Known data: 10 calls in the last hour, 2 two days ago, 1 in another workspace."""
    acct = await make_account()
    other = await make_account(workspace="Other")
    ws = acct.workspace_id
    latencies = [10, 20, 30, 40, 50, 60, 70, 80, 90, 1000]
    for i, latency in enumerate(latencies):
        db_session.add(
            _log(
                ws,
                ago=timedelta(minutes=5 + i),
                latency_ms=float(latency),
                model_name="gpt-x" if i < 6 else "llama3.2",
                provider_name="OpenAI" if i < 6 else "Ollama",
                cost_usd=0.01 if i < 6 else 0.0,
                success=i not in (2, 7),
                error_type="server" if i == 2 else ("cancelled" if i == 7 else None),
            )
        )
    for i in range(2):
        db_session.add(_log(ws, ago=timedelta(days=2, minutes=i), cost_usd=1.0))
    db_session.add(_log(other.workspace_id, cost_usd=99.0))
    await db_session.commit()
    return acct


async def _get(client, acct, path, **params):
    resp = await client.get(path, params=params, headers=acct.headers)
    assert resp.status_code == 200, resp.text
    return resp.json()


# ── Window parsing ──────────────────────────────────────────


def test_window_defaults_to_last_24_hours():
    w = resolve_window(now=NOW)
    assert w.end == NOW
    assert w.duration == timedelta(hours=24)


def test_window_from_to():
    w = resolve_window(start="2026-01-01T00:00:00Z", end="2026-01-02T00:00:00Z")
    assert w.duration == timedelta(days=1)
    assert w.start.tzinfo is not None


@pytest.mark.parametrize(
    "kwargs",
    [
        {"hours": 0},
        {"start": "2026-01-02T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
        {"start": "yesterday"},
        {"end": "2026-01-01T00:00:00Z"},
        {"start": "2020-01-01T00:00:00Z", "end": "2026-01-01T00:00:00Z"},
    ],
)
def test_invalid_windows(kwargs):
    with pytest.raises(ValidationException):
        resolve_window(**kwargs)


@pytest.mark.parametrize(
    "hours,seconds", [(1, 60), (6, 300), (24, 3600), (24 * 7, 21600), (24 * 30, 86400)]
)
def test_automatic_bucket_size(hours, seconds):
    assert bucket_seconds(Window(NOW - timedelta(hours=hours), NOW)) == seconds


def test_too_many_explicit_buckets_rejected():
    with pytest.raises(ValidationException):
        bucket_seconds(Window(NOW - timedelta(days=30), NOW), "1m")


# ── Summary ─────────────────────────────────────────────────


async def test_summary_over_the_window(client, seeded):
    s = await _get(client, seeded, "/analytics/summary", hours=1)

    assert s["total_requests"] == 10
    assert s["total_cost_usd"] == pytest.approx(0.06)
    assert s["total_errors"] == 1
    assert s["total_cancelled"] == 1
    # Cancelled streams are not errors: 1 error out of 9 considered calls.
    assert s["error_rate_pct"] == pytest.approx(11.11)
    assert s["avg_latency_ms"] == pytest.approx(145.0)
    # Nearest rank: p50 -> 5th of 10, p95 -> 10th of 10.
    assert s["p50_latency_ms"] == 50.0
    assert s["p95_latency_ms"] == 1000.0
    assert s["input_tokens"] == 100
    assert s["output_tokens"] == 50


async def test_hours_parameter_changes_the_result(client, seeded):
    """Regression: `hours` used to be ignored."""
    one_hour = await _get(client, seeded, "/analytics/summary", hours=1)
    three_days = await _get(client, seeded, "/analytics/summary", hours=72)
    assert one_hour["total_requests"] == 10
    assert three_days["total_requests"] == 12
    assert three_days["total_cost_usd"] == pytest.approx(2.06)


async def test_from_to_window(client, seeded):
    s = await _get(
        client,
        seeded,
        "/analytics/summary",
        **{
            "from": (NOW - timedelta(days=3)).isoformat(),
            "to": (NOW - timedelta(days=1)).isoformat(),
        },
    )
    assert s["total_requests"] == 2


async def test_model_breakdown_is_dynamic(client, seeded):
    """Regression: only "qwen" and "gemini" used to be reported."""
    s = await _get(client, seeded, "/analytics/summary", hours=1)
    breakdown = s["model_breakdown"]
    assert set(breakdown) == {"OpenAI/gpt-x", "Ollama/llama3.2"}
    assert breakdown["OpenAI/gpt-x"]["requests"] == 6
    assert breakdown["OpenAI/gpt-x"]["cost"] == pytest.approx(0.06)
    assert breakdown["OpenAI/gpt-x"]["errors"] == 1
    assert breakdown["Ollama/llama3.2"]["requests"] == 4
    assert breakdown["Ollama/llama3.2"]["model"] == "llama3.2"


async def test_no_row_cap(client, make_account, db_session):
    """Regression: only the newest 500 rows used to be aggregated."""
    acct = await make_account()
    for i in range(650):
        db_session.add(_log(acct.workspace_id, ago=timedelta(seconds=i + 1)))
    await db_session.commit()
    s = await _get(client, acct, "/analytics/summary", hours=1)
    assert s["total_requests"] == 650
    assert s["total_cost_usd"] == pytest.approx(6.5)


async def test_previous_period_and_deltas(client, make_account, db_session):
    acct = await make_account()
    ws = acct.workspace_id
    for i in range(4):  # current hour: 4 calls at $0.01
        db_session.add(_log(ws, ago=timedelta(minutes=10 + i)))
    for i in range(2):  # previous hour: 2 calls at $0.01
        db_session.add(_log(ws, ago=timedelta(minutes=70 + i)))
    await db_session.commit()

    s = await _get(client, acct, "/analytics/summary", hours=1)
    assert s["previous"]["total_requests"] == 2
    assert s["deltas_pct"]["total_requests"] == 100.0
    assert s["deltas_pct"]["total_cost_usd"] == 100.0
    assert s["deltas_pct"]["avg_latency_ms"] == 0.0


async def test_deltas_are_null_without_a_baseline(client, seeded):
    s = await _get(client, seeded, "/analytics/summary", hours=1)
    assert s["previous"]["total_requests"] == 0
    assert s["deltas_pct"]["total_requests"] is None


async def test_empty_workspace(client, make_account):
    acct = await make_account()
    s = await _get(client, acct, "/analytics/summary")
    assert s["total_requests"] == 0
    assert s["p95_latency_ms"] is None
    assert s["error_rate_pct"] == 0.0
    assert s["model_breakdown"] == {}


async def test_summary_filters(client, seeded):
    s = await _get(client, seeded, "/analytics/summary", hours=1, provider="Ollama")
    assert s["total_requests"] == 4
    assert set(s["model_breakdown"]) == {"Ollama/llama3.2"}


async def test_workspace_isolation(client, seeded, make_account):
    s = await _get(client, seeded, "/analytics/summary", hours=72)
    assert s["total_cost_usd"] < 99  # the other workspace's $99 call isn't counted


async def test_invalid_window_is_400(client, seeded):
    resp = await client.get(
        "/analytics/summary", params={"from": "nope"}, headers=seeded.headers
    )
    assert resp.status_code == 400


# ── Timeseries ──────────────────────────────────────────────


async def test_timeseries_buckets_are_zero_filled(client, make_account, db_session):
    acct = await make_account()
    start = datetime(2026, 3, 1, 0, 0, tzinfo=UTC)
    for minutes, cost in [(5, 0.1), (10, 0.2), (130, 0.4)]:
        db_session.add(
            LLMLog(
                workspace_id=acct.workspace_id,
                created_at=start + timedelta(minutes=minutes),
                model_name="m",
                cost_usd=cost,
                latency_ms=minutes * 1.0,
            )
        )
    await db_session.commit()

    ts = await _get(
        client,
        acct,
        "/analytics/timeseries",
        bucket="1h",
        **{
            "from": start.isoformat(),
            "to": (start + timedelta(hours=4)).isoformat(),
        },
    )
    assert ts["bucket_seconds"] == 3600
    assert [b["requests"] for b in ts["buckets"]] == [2, 0, 1, 0]
    assert ts["buckets"][0]["cost_usd"] == pytest.approx(0.3)
    assert ts["buckets"][0]["avg_latency_ms"] == 7.5
    assert ts["buckets"][1]["avg_latency_ms"] is None
    assert ts["buckets"][0]["ts"] == "2026-03-01T00:00:00+00:00"
    # Flat arrays for the current chart stay in step with the buckets.
    assert ts["request_counts"] == [2, 0, 1, 0]
    assert len(ts["timestamps"]) == 4


async def test_timeseries_default_window(client, seeded):
    ts = await _get(client, seeded, "/analytics/timeseries")
    assert ts["bucket_seconds"] == 3600
    assert sum(b["requests"] for b in ts["buckets"]) == 10


# ── Logs ────────────────────────────────────────────────────


async def test_logs_are_paginated_newest_first(client, seeded):
    page1 = await _get(client, seeded, "/analytics/logs", hours=1, page_size=4)
    page3 = await _get(client, seeded, "/analytics/logs", hours=1, page_size=4, page=3)

    assert page1["total"] == 10
    assert len(page1["items"]) == 4
    assert len(page3["items"]) == 2
    stamps = [i["timestamp"] for i in page1["items"]]
    assert stamps == sorted(stamps, reverse=True)


@pytest.mark.parametrize(
    "params,total",
    [
        ({"status": "error"}, 1),
        ({"status": "cancelled"}, 1),
        ({"status": "success"}, 8),
        ({"model": "llama3.2"}, 4),
        ({"provider": "OpenAI"}, 6),
        ({"q": "HELLO"}, 10),
        ({"q": "no such text"}, 0),
    ],
)
async def test_log_filters(client, seeded, params, total):
    body = await _get(client, seeded, "/analytics/logs", hours=1, **params)
    assert body["total"] == total


async def test_bad_status_filter_is_400(client, seeded):
    resp = await client.get(
        "/analytics/logs", params={"status": "weird"}, headers=seeded.headers
    )
    assert resp.status_code == 400


async def test_filter_options(client, seeded):
    body = await _get(client, seeded, "/analytics/filters", hours=1)
    assert body == {"models": ["gpt-x", "llama3.2"], "providers": ["Ollama", "OpenAI"]}


# ── CSV export ──────────────────────────────────────────────


async def test_csv_export_of_the_filtered_set(client, seeded):
    resp = await client.get(
        "/analytics/logs.csv",
        params={"hours": 1, "provider": "Ollama"},
        headers=seeded.headers,
    )
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "attachment" in resp.headers["content-disposition"]
    rows = list(csv.DictReader(io.StringIO(resp.text)))
    assert len(rows) == 4
    assert {r["provider_name"] for r in rows} == {"Ollama"}


async def test_csv_neutralises_formulas(client, make_account, db_session):
    acct = await make_account()
    db_session.add(_log(acct.workspace_id, prompt_preview='=HYPERLINK("http://x")'))
    await db_session.commit()
    resp = await client.get("/analytics/logs.csv", headers=acct.headers)
    (row,) = list(csv.DictReader(io.StringIO(resp.text)))
    assert row["prompt_preview"].startswith("'=")
