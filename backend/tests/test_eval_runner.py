"""
Tests for the eval runner: execution, scoring, retries, caching, concurrency,
cancel/resume and the runs API. The model is the fake OpenAI-compatible server.
"""

import asyncio
import json

import httpx
import pytest
from sqlalchemy import func, select

from llmwatch.config import settings
from llmwatch.db.models import EvalResult, EvalRun, Model
from llmwatch.evals import runner
from llmwatch.evals.runner import RunExecutor, VariantSpec, create_runs
from llmwatch.llm import LLMClient
from llmwatch.providers import service as provider_service
from tests.fake_llm import FakeProvider

SUITE = """
name: capitals
prompt: "Capital of {{ country }}? Answer with the city only."
cases:
  - id: fr
    vars: {country: France}
    expected: Paris
  - id: de
    vars: {country: Germany}
    expected: Berlin
  - id: jp
    vars: {country: Japan}
    expected: Tokyo
"""


@pytest.fixture
async def setup(client, make_account, add_model, fake_llm):
    """Account + priced model ($1/$2 per 1M) + the capitals suite."""
    acct = await make_account()
    await add_model(acct, input_price=1.0, output_price=2.0)
    suite = (
        await client.post(
            "/evals/suites/import", json={"content": SUITE}, headers=acct.headers
        )
    ).json()
    return acct, suite


async def _new_run(acct, suite, *, repeats=1, concurrency=4, variants=None, **kw):
    from llmwatch.db.engine import get_sessionmaker

    async with get_sessionmaker()() as session:
        runs = await create_runs(
            session,
            acct.workspace_id,
            suite_id=suite["id"],
            variants=variants or [VariantSpec(model="fake-model")],
            repeats=repeats,
            concurrency=concurrency,
            **kw,
        )
        await session.commit()
        return [r.id for r in runs]


def _answers(fake, *answers, usage=(10, 2)):
    for answer in answers:
        fake.reply(answer, usage=usage)


async def _results(db_session, run_id):
    db_session.expire_all()
    rows = await db_session.execute(
        select(EvalResult)
        .where(EvalResult.run_id == run_id)
        .order_by(EvalResult.created_at)
    )
    return rows.scalars().all()


async def _run(db_session, run_id):
    db_session.expire_all()
    return await db_session.get(EvalRun, run_id)


def _no_sleep():
    calls = []

    async def sleep(delay):
        calls.append(delay)

    return sleep, calls


# ── Execution and scoring ───────────────────────────────────


async def test_run_scores_every_case(setup, fake_llm, db_session):
    acct, suite = setup
    _answers(fake_llm, "Paris", "Munich", "Tokyo")
    (run_id,) = await _new_run(acct, suite, concurrency=1)

    status = await RunExecutor(run_id, acct.workspace_id).execute()

    assert status == "completed"
    run = await _run(db_session, run_id)
    assert run.completed_items == 3
    assert run.failed_items == 0
    assert run.pass_rate == pytest.approx(2 / 3)
    assert run.mean_score == pytest.approx(2 / 3)
    # 3 calls x (10 in + 2 out) at $1 / $2 per 1M
    assert run.total_cost_usd == pytest.approx(3 * (10 / 1e6 + 2 * 2 / 1e6))
    assert run.total_tokens == 36
    results = await _results(db_session, run_id)
    by_output = {r.output: r for r in results}
    assert by_output["Munich"].passed is False
    assert by_output["Munich"].evaluator_results[0]["reason"] == "Expected 'Berlin'"
    assert by_output["Paris"].evaluator_results[0]["type"] == "exact_match"


async def test_requests_render_the_template(setup, fake_llm):
    acct, suite = setup
    (run_id,) = await _new_run(acct, suite, concurrency=1)
    await RunExecutor(run_id, acct.workspace_id).execute()
    prompts = sorted(r["messages"][-1]["content"] for r in fake_llm.requests)
    assert prompts[0] == "Capital of France? Answer with the city only."


async def test_variant_params_are_sent(setup, fake_llm):
    acct, suite = setup
    (run_id,) = await _new_run(
        acct,
        suite,
        variants=[VariantSpec("fake-model", {"temperature": 0, "max_tokens": 5})],
    )
    await RunExecutor(run_id, acct.workspace_id).execute()
    assert {r["temperature"] for r in fake_llm.requests} == {0}
    assert {r["max_tokens"] for r in fake_llm.requests} == {5}


async def test_repeats_multiply_items(setup, fake_llm, db_session):
    acct, suite = setup
    (run_id,) = await _new_run(acct, suite, repeats=3)
    await RunExecutor(run_id, acct.workspace_id).execute()
    run = await _run(db_session, run_id)
    assert run.total_items == run.completed_items == 9
    assert len(fake_llm.requests) == 9  # each repeat is a real sample


async def test_pricing_is_frozen_at_creation(setup, fake_llm, db_session):
    acct, suite = setup
    (run_id,) = await _new_run(acct, suite)
    model = (await db_session.execute(select(Model))).scalar_one()
    model.input_price_per_mtok = 1000.0
    await db_session.commit()

    await RunExecutor(run_id, acct.workspace_id).execute()

    run = await _run(db_session, run_id)
    assert run.pricing_snapshot["input_price_per_mtok"] == 1.0
    assert run.total_cost_usd == pytest.approx(3 * (5 / 1e6 + 2 * 2 / 1e6))


async def test_unpriced_model_costs_zero_and_says_so(
    client, make_account, add_model, fake_llm, db_session
):
    acct = await make_account()
    await add_model(acct, input_price=None, output_price=None)
    suite = (
        await client.post(
            "/evals/suites/import", json={"content": SUITE}, headers=acct.headers
        )
    ).json()
    (run_id,) = await _new_run(acct, suite)
    await RunExecutor(run_id, acct.workspace_id).execute()
    run = await _run(db_session, run_id)
    assert run.pricing_snapshot["input_price_per_mtok"] is None
    assert run.total_cost_usd == 0


# ── Retries ─────────────────────────────────────────────────


async def test_rate_limit_retry_honours_retry_after(
    setup, fake_llm, db_session, monkeypatch
):
    acct, suite = setup
    monkeypatch.setattr(settings, "eval_retry_base_s", 0.5)
    fake_llm.fail(429, retry_after="7")
    _answers(fake_llm, "Paris", "Berlin", "Tokyo")
    (run_id,) = await _new_run(acct, suite, concurrency=1)
    sleep, delays = _no_sleep()

    await RunExecutor(
        run_id, acct.workspace_id, sleep=sleep, rand=lambda: 0.0
    ).execute()

    assert delays == [7.0]  # Retry-After beats the (zero) jitter
    run = await _run(db_session, run_id)
    assert run.failed_items == 0
    assert run.pass_rate == 1.0


async def test_backoff_is_exponential_with_full_jitter(setup, fake_llm, monkeypatch):
    acct, suite = setup
    monkeypatch.setattr(settings, "eval_retry_base_s", 1.0)
    monkeypatch.setattr(settings, "eval_retry_max_s", 3.0)
    for _ in range(3):
        fake_llm.fail(503)
    (run_id,) = await _new_run(acct, suite, concurrency=1)
    sleep, delays = _no_sleep()

    await RunExecutor(
        run_id, acct.workspace_id, sleep=sleep, rand=lambda: 1.0
    ).execute()

    assert delays == [1.0, 2.0, 3.0]  # base * 2^n, capped at 3


async def test_non_retryable_errors_fail_the_item_immediately(
    setup, fake_llm, db_session
):
    acct, suite = setup
    fake_llm.fail(400, message="bad request")
    _answers(fake_llm, "Berlin", "Tokyo")
    (run_id,) = await _new_run(acct, suite, concurrency=1)
    sleep, delays = _no_sleep()

    status = await RunExecutor(run_id, acct.workspace_id, sleep=sleep).execute()

    assert status == "completed"
    assert delays == []
    assert len(fake_llm.requests) == 3
    run = await _run(db_session, run_id)
    assert run.failed_items == 1
    errored = [r for r in await _results(db_session, run_id) if r.error]
    assert errored[0].error.startswith("bad_request")
    assert errored[0].score == 0 and errored[0].passed is False


async def test_exhausted_retries_fail_the_item(
    setup, fake_llm, db_session, monkeypatch
):
    acct, suite = setup
    monkeypatch.setattr(settings, "eval_max_retries", 2)
    for _ in range(3):
        fake_llm.fail(500)
    _answers(fake_llm, "Berlin", "Tokyo")
    (run_id,) = await _new_run(acct, suite, concurrency=1)
    sleep, delays = _no_sleep()

    await RunExecutor(run_id, acct.workspace_id, sleep=sleep).execute()

    assert len(delays) == 2
    run = await _run(db_session, run_id)
    assert run.failed_items == 1


async def test_all_items_failing_marks_the_run_failed(
    setup, fake_llm, db_session, monkeypatch
):
    acct, suite = setup
    for _ in range(3):
        fake_llm.fail(401, message="bad key")
    (run_id,) = await _new_run(acct, suite)
    assert await RunExecutor(run_id, acct.workspace_id).execute() == "failed"
    assert "Every item failed" in (await _run(db_session, run_id)).error


# ── Cache ───────────────────────────────────────────────────


async def test_rerun_is_served_from_cache(setup, fake_llm, db_session):
    acct, suite = setup
    _answers(fake_llm, "Paris", "Berlin", "Tokyo")
    (first,) = await _new_run(acct, suite, concurrency=1)
    await RunExecutor(first, acct.workspace_id).execute()
    calls_after_first = len(fake_llm.requests)

    (second,) = await _new_run(acct, suite)
    await RunExecutor(second, acct.workspace_id).execute()

    assert len(fake_llm.requests) == calls_after_first  # nothing new sent
    results = await _results(db_session, second)
    assert all(r.cached for r in results)
    assert sorted(r.output for r in results) == ["Berlin", "Paris", "Tokyo"]
    a = await _run(db_session, first)
    first_metrics = (a.mean_score, a.total_cost_usd)
    b = await _run(db_session, second)
    assert (b.mean_score, b.total_cost_usd) == first_metrics


async def test_cache_key_changes_with_params(setup, fake_llm):
    acct, suite = setup
    (r1,) = await _new_run(acct, suite)
    await RunExecutor(r1, acct.workspace_id).execute()
    (r2,) = await _new_run(
        acct, suite, variants=[VariantSpec("fake-model", {"temperature": 0.7})]
    )
    await RunExecutor(r2, acct.workspace_id).execute()
    assert len(fake_llm.requests) == 6


async def test_cache_can_be_turned_off(setup, fake_llm):
    acct, suite = setup
    for _ in range(2):
        (run_id,) = await _new_run(acct, suite, use_cache=False)
        await RunExecutor(run_id, acct.workspace_id).execute()
    assert len(fake_llm.requests) == 6


async def test_cache_is_scoped_to_the_workspace(
    setup, client, make_account, add_model, fake_llm
):
    acct, suite = setup
    (run_id,) = await _new_run(acct, suite)
    await RunExecutor(run_id, acct.workspace_id).execute()

    other = await make_account(workspace="Other")
    await add_model(other)
    other_suite = (
        await client.post(
            "/evals/suites/import", json={"content": SUITE}, headers=other.headers
        )
    ).json()
    (other_run,) = await _new_run(other, other_suite)
    await RunExecutor(other_run, other.workspace_id).execute()
    assert len(fake_llm.requests) == 6  # no cross-tenant cache hits


# ── Concurrency ─────────────────────────────────────────────


class SlowTransport(httpx.AsyncBaseTransport):
    """Answers after a short delay and records peak concurrency."""

    def __init__(self):
        self.in_flight = 0
        self.peak = 0
        self.calls = 0
        self._fake = FakeProvider()

    async def handle_async_request(self, request):
        self.in_flight += 1
        self.calls += 1
        self.peak = max(self.peak, self.in_flight)
        try:
            await asyncio.sleep(0.02)
            body = json.loads(request.content)
            return httpx.Response(
                200, json=self._fake._completion(body, self._fake._next())
            )
        finally:
            self.in_flight -= 1


@pytest.fixture
def slow_transport(monkeypatch):
    transport = SlowTransport()
    monkeypatch.setattr(
        provider_service,
        "make_client",
        lambda config: LLMClient(
            config, http_client=httpx.AsyncClient(transport=transport)
        ),
    )
    return transport


MANY = "name: many\nprompt: 'Say {{ n }}'\ncases:\n" + "".join(
    f"  - {{id: c{i}, vars: {{n: '{i}'}}, expected: ok}}\n" for i in range(12)
)


async def test_run_concurrency_is_bounded(
    client, make_account, add_model, slow_transport
):
    acct = await make_account()
    await add_model(acct)
    suite = (
        await client.post(
            "/evals/suites/import", json={"content": MANY}, headers=acct.headers
        )
    ).json()
    (run_id,) = await _new_run(acct, suite, concurrency=3)
    await RunExecutor(run_id, acct.workspace_id).execute()
    assert slow_transport.calls == 12
    assert slow_transport.peak == 3


async def test_provider_concurrency_caps_parallel_runs(
    client, make_account, add_model, slow_transport, monkeypatch
):
    monkeypatch.setattr(settings, "eval_provider_concurrency", 2)
    acct = await make_account()
    await add_model(acct)
    suite = (
        await client.post(
            "/evals/suites/import", json={"content": MANY}, headers=acct.headers
        )
    ).json()
    run_ids = await _new_run(
        acct,
        suite,
        concurrency=8,
        variants=[VariantSpec("fake-model", {"temperature": t}) for t in (0, 1)],
    )
    await asyncio.gather(
        *(RunExecutor(r, acct.workspace_id).execute() for r in run_ids)
    )
    assert slow_transport.calls == 24
    assert slow_transport.peak == 2  # one provider, two runs, capped together


# ── Cancel and resume ───────────────────────────────────────


async def test_cancel_stops_remaining_items_and_resume_finishes(
    client, make_account, add_model, slow_transport, db_session
):
    acct = await make_account()
    await add_model(acct)
    suite = (
        await client.post(
            "/evals/suites/import", json={"content": MANY}, headers=acct.headers
        )
    ).json()
    (run_id,) = await _new_run(acct, suite, concurrency=1)

    task = runner.start(run_id, acct.workspace_id)
    while slow_transport.calls < 3:
        await asyncio.sleep(0.005)
    resp = await client.post(f"/evals/runs/{run_id}/cancel", headers=acct.headers)
    assert resp.json()["status"] == "cancelling"
    await task

    run = await _run(db_session, run_id)
    assert run.status == "cancelled"
    done_before = run.completed_items
    assert 3 <= done_before < 12

    resp = await client.post(f"/evals/runs/{run_id}/resume", headers=acct.headers)
    assert resp.status_code == 202
    await runner.wait(run_id)

    run = await _run(db_session, run_id)
    assert run.status == "completed"
    assert run.completed_items == 12
    assert slow_transport.calls == 12  # done items were not repeated
    count = (
        await db_session.execute(
            select(func.count())
            .select_from(EvalResult)
            .where(EvalResult.run_id == run_id)
        )
    ).scalar_one()
    assert count == 12


async def test_resume_can_retry_errored_items(setup, fake_llm, db_session):
    acct, suite = setup
    fake_llm.fail(400)
    _answers(fake_llm, "Berlin", "Tokyo")
    (run_id,) = await _new_run(acct, suite, concurrency=1)
    await RunExecutor(run_id, acct.workspace_id).execute()
    assert (await _run(db_session, run_id)).failed_items == 1

    from llmwatch.db.engine import get_sessionmaker

    async with get_sessionmaker()() as session:
        await runner.prepare_resume(
            session, acct.workspace_id, run_id, retry_errors=True
        )
    fake_llm.reply("Paris")
    await RunExecutor(run_id, acct.workspace_id).execute()

    run = await _run(db_session, run_id)
    assert run.failed_items == 0
    assert run.completed_items == 3
    assert run.pass_rate == 1.0


async def test_interrupted_runs_are_marked_at_startup(setup, db_session):
    acct, suite = setup
    (run_id,) = await _new_run(acct, suite)
    run = await _run(db_session, run_id)
    run.status = "running"
    await db_session.commit()

    assert await runner.mark_interrupted_runs() == 1
    assert (await _run(db_session, run_id)).status == "interrupted"


# ── Model-backed evaluators through the runner ──────────────


JUDGED = """
name: judged
prompt: "Explain {{ topic }} briefly."
cases:
  - id: dns
    vars: {topic: DNS}
    assert:
      - type: llm_judge
        value: Is the explanation accurate?
        model: Judge/judge-model
"""


async def test_llm_judge_uses_the_registry_judge_and_is_cached(
    client, make_account, add_model, fake_llm, db_session
):
    acct = await make_account()
    await add_model(acct)
    await add_model(acct, "judge-model", provider_name="Judge")
    suite = (
        await client.post(
            "/evals/suites/import", json={"content": JUDGED}, headers=acct.headers
        )
    ).json()
    fake_llm.reply("DNS maps names to addresses.")
    fake_llm.reply('{"reasoning": "Accurate.", "score": 9}')

    (run_id,) = await _new_run(acct, suite)
    await RunExecutor(run_id, acct.workspace_id).execute()

    (result,) = await _results(db_session, run_id)
    assert result.passed
    assert result.score == pytest.approx(0.9)
    judge_request = fake_llm.requests[1]
    assert judge_request["model"] == "judge-model"
    assert judge_request["temperature"] == 0

    (again,) = await _new_run(acct, suite)
    await RunExecutor(again, acct.workspace_id).execute()
    assert len(fake_llm.requests) == 2  # candidate and judge both cached


# ── API ─────────────────────────────────────────────────────


async def test_runs_api_end_to_end(setup, client, fake_llm):
    acct, suite = setup
    _answers(fake_llm, "Paris", "Berlin", "Osaka")
    resp = await client.post(
        "/evals/runs",
        json={
            "suite_id": suite["id"],
            "variants": [{"model": "fake-model"}],
            "concurrency": 1,
        },
        headers=acct.headers,
    )
    assert resp.status_code == 202
    (run,) = resp.json()["runs"]
    assert run["status"] == "pending"
    assert run["total_items"] == 3
    await runner.wait(run["id"])

    detail = (await client.get(f"/evals/runs/{run['id']}", headers=acct.headers)).json()
    assert detail["status"] == "completed"
    assert detail["pass_rate"] == pytest.approx(2 / 3)

    failed = (
        await client.get(
            f"/evals/runs/{run['id']}/results",
            params={"status": "failed"},
            headers=acct.headers,
        )
    ).json()
    assert failed["total"] == 1
    item = failed["items"][0]
    assert item["case_id"] == "jp"
    assert item["output"] == "Osaka"
    assert item["expected"] == "Tokyo"
    assert item["evaluator_results"][0]["reason"] == "Expected 'Tokyo'"

    listing = (
        await client.get(
            "/evals/runs", params={"suite_id": suite["id"]}, headers=acct.headers
        )
    ).json()
    assert [r["id"] for r in listing["runs"]] == [run["id"]]


async def test_multiple_variants_share_a_group(setup, client, add_model, fake_llm):
    acct, suite = setup
    await add_model(acct, "other-model")
    body = {
        "suite_id": suite["id"],
        "variants": [
            {"model": "fake-model"},
            {"model": "other-model", "temperature": 0.2},
        ],
    }
    runs = (await client.post("/evals/runs", json=body, headers=acct.headers)).json()[
        "runs"
    ]
    for r in runs:
        await runner.wait(r["id"])
    assert len({r["group_id"] for r in runs}) == 1
    assert runs[1]["variant"]["params"] == {"temperature": 0.2}


async def test_unknown_model_is_rejected_before_running(setup, client):
    acct, suite = setup
    resp = await client.post(
        "/evals/runs",
        json={"suite_id": suite["id"], "variants": [{"model": "nope"}]},
        headers=acct.headers,
    )
    assert resp.status_code == 400


async def test_runs_are_isolated(setup, client, make_account):
    acct, suite = setup
    (run_id,) = await _new_run(acct, suite)
    other = await make_account(workspace="Other")
    for method, path in [
        ("get", f"/evals/runs/{run_id}"),
        ("get", f"/evals/runs/{run_id}/results"),
        ("post", f"/evals/runs/{run_id}/cancel"),
        ("delete", f"/evals/runs/{run_id}"),
    ]:
        assert (
            await client.request(method, path, headers=other.headers)
        ).status_code == 404
    resp = await client.post(
        "/evals/runs",
        json={"suite_id": suite["id"], "variants": [{"model": "fake-model"}]},
        headers=other.headers,
    )
    assert resp.status_code == 404


async def test_delete_run(setup, client, fake_llm):
    acct, suite = setup
    (run_id,) = await _new_run(acct, suite)
    await RunExecutor(run_id, acct.workspace_id).execute()
    assert (
        await client.delete(f"/evals/runs/{run_id}", headers=acct.headers)
    ).status_code == 204
    assert (
        await client.get(f"/evals/runs/{run_id}", headers=acct.headers)
    ).status_code == 404
