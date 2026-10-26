"""
Tests for the comparison statistics (against hand-computed values) and the
run comparison API.
"""

import math
import random
import statistics

import pytest
from sqlalchemy import select

from llmwatch.db.models import EvalCase, EvalResult, EvalRun
from llmwatch.evals.runner import VariantSpec, create_runs
from llmwatch.evals.stats import mcnemar, paired_bootstrap, relative_change

# ── McNemar ─────────────────────────────────────────────────


def test_mcnemar_exact_small_counts():
    # n = 10, k = min(b, c) = 1: p = 2 * (C(10,0) + C(10,1)) / 2^10 = 22/1024
    r = mcnemar(1, 9)
    assert r.test == "exact"
    assert r.p_value == pytest.approx(22 / 1024)
    assert r.significant()


def test_mcnemar_exact_all_one_direction():
    # n = 5, k = 0: p = 2 / 32
    assert mcnemar(0, 5).p_value == pytest.approx(0.0625)
    assert not mcnemar(0, 5).significant()


def test_mcnemar_exact_balanced_is_capped_at_one():
    assert mcnemar(3, 3).p_value == 1.0


def test_mcnemar_chi_squared_with_continuity_correction():
    # statistic = (|10 - 30| - 1)^2 / 40 = 9.025; chi2(1) survival = erfc(sqrt(x/2))
    r = mcnemar(10, 30)
    assert r.test == "chi2_cc"
    assert r.p_value == pytest.approx(math.erfc(math.sqrt(9.025 / 2)))
    assert r.p_value == pytest.approx(0.002663, rel=1e-3)


def test_mcnemar_switches_to_chi2_at_25():
    assert mcnemar(12, 12).test == "exact"
    r = mcnemar(12, 13)
    assert r.test == "chi2_cc"
    assert r.p_value == pytest.approx(1.0)  # (|-1| - 1)^2 = 0


def test_mcnemar_no_discordant_cases():
    r = mcnemar(0, 0)
    assert (r.p_value, r.test) == (1.0, "none")


# ── Bootstrap ───────────────────────────────────────────────


def test_bootstrap_constant_deltas_have_a_zero_width_interval():
    r = paired_bootstrap([0.25] * 30)
    assert (r.mean, r.low, r.high) == pytest.approx((0.25, 0.25, 0.25))
    assert r.significant


def test_bootstrap_symmetric_noise_is_not_significant():
    r = paired_bootstrap([-1.0, 1.0] * 50)
    assert r.mean == pytest.approx(0.0)
    assert r.low < 0 < r.high
    assert not r.significant


def test_bootstrap_matches_the_normal_approximation_for_large_n():
    rng = random.Random(42)
    deltas = [rng.gauss(0.1, 0.5) for _ in range(400)]
    r = paired_bootstrap(deltas, resamples=20_000)
    mean = statistics.fmean(deltas)
    half_width = 1.96 * statistics.stdev(deltas) / math.sqrt(len(deltas))
    assert r.mean == pytest.approx(mean)
    assert r.low == pytest.approx(mean - half_width, abs=0.01)
    assert r.high == pytest.approx(mean + half_width, abs=0.01)


def test_bootstrap_is_reproducible_with_a_seed():
    deltas = [0.1, -0.2, 0.3, 0.0, 0.5, -0.1, 0.2]
    assert paired_bootstrap(deltas, seed=7) == paired_bootstrap(deltas, seed=7)


def test_bootstrap_single_case():
    r = paired_bootstrap([0.4])
    assert (r.low, r.high, r.resamples) == (0.4, 0.4, 0)


def test_bootstrap_needs_data():
    with pytest.raises(ValueError):
        paired_bootstrap([])


def test_relative_change():
    assert relative_change(1.5, 1.0) == pytest.approx(50.0)
    assert relative_change(0.5, 1.0) == pytest.approx(-50.0)
    assert relative_change(1.0, 0.0) is None
    assert relative_change(None, 1.0) is None


# ── Comparison API ──────────────────────────────────────────

SUITE = "name: cmp\nprompt: '{{ q }}'\ncases:\n" + "".join(
    f"  - {{id: c{i:02d}, vars: {{q: '{i}'}}, expected: ok}}\n" for i in range(40)
)


@pytest.fixture
async def suite_and_runs(client, make_account, add_model, db_session):
    acct = await make_account()
    await add_model(acct, input_price=1.0, output_price=2.0)
    await add_model(acct, "cheap-model", input_price=0.1, output_price=0.2)
    suite = (
        await client.post(
            "/evals/suites/import", json={"content": SUITE}, headers=acct.headers
        )
    ).json()

    async def make_run(model, outcomes, cost=0.001, latency=100.0, repeats=1):
        """outcomes: case index -> (score, passed); every case gets `repeats` rows."""
        from llmwatch.db.engine import get_sessionmaker

        async with get_sessionmaker()() as session:
            (run,) = await create_runs(
                session,
                acct.workspace_id,
                suite_id=suite["id"],
                variants=[VariantSpec(model=model)],
                repeats=repeats,
            )
            cases = (
                (
                    await session.execute(
                        select(EvalCase)
                        .where(EvalCase.suite_version_id == run.suite_version_id)
                        .order_by(EvalCase.position)
                    )
                )
                .scalars()
                .all()
            )
            for i, case in enumerate(cases):
                if i not in outcomes:
                    continue
                for r in range(repeats):
                    score, passed = (
                        outcomes[i] if not callable(outcomes[i]) else outcomes[i](r)
                    )
                    session.add(
                        EvalResult(
                            workspace_id=acct.workspace_id,
                            run_id=run.id,
                            case_id=case.id,
                            repeat_index=r,
                            score=score,
                            passed=passed,
                            cost_usd=cost,
                            latency_ms=latency,
                        )
                    )
            run.status = "completed"
            await session.commit()
            return run.id

    return acct, suite, make_run


async def _compare(client, acct, baseline, candidate):
    resp = await client.get(
        "/evals/compare",
        params={"baseline": baseline, "candidate": candidate},
        headers=acct.headers,
    )
    assert resp.status_code == 200, resp.text
    return resp.json()


async def test_a_real_improvement_is_significant(client, suite_and_runs):
    acct, _, make_run = suite_and_runs
    base = await make_run(
        "fake-model", {i: (1.0, True) if i < 20 else (0.0, False) for i in range(40)}
    )
    cand = await make_run(
        "fake-model", {i: (1.0, True) if i < 36 else (0.0, False) for i in range(40)}
    )

    body = await _compare(client, acct, base, cand)

    assert body["paired_cases"] == 40
    assert body["score"]["delta"] == pytest.approx(0.4)
    assert body["score"]["ci_low"] > 0
    assert body["score"]["significant"] is True
    assert body["pass_rate"]["fixes"] == 16
    assert body["pass_rate"]["regressions"] == 0
    assert body["pass_rate"]["test"] == "exact"
    assert body["pass_rate"]["p_value"] == pytest.approx(2 / 2**16)
    assert body["verdict"] == "improved"
    fixed = [c for c in body["cases"] if c["change"] == "fixed"]
    assert len(fixed) == 16


async def test_noise_is_reported_as_no_significant_difference(client, suite_and_runs):
    acct, _, make_run = suite_and_runs
    # Two cases flip each way: same pass rate, small random-looking changes.
    base = await make_run(
        "fake-model", {i: (1.0, True) if i % 2 else (0.0, False) for i in range(40)}
    )
    flipped = {i: (1.0, True) if i % 2 else (0.0, False) for i in range(40)}
    flipped[0], flipped[1], flipped[2], flipped[3] = (
        (1.0, True),
        (0.0, False),
        (1.0, True),
        (0.0, False),
    )
    cand = await make_run("fake-model", flipped)

    body = await _compare(client, acct, base, cand)

    assert body["score"]["delta"] == pytest.approx(0.0)
    assert body["score"]["significant"] is False
    assert body["pass_rate"]["fixes"] == 2
    assert body["pass_rate"]["regressions"] == 2
    assert body["pass_rate"]["p_value"] == 1.0
    assert body["verdict"] == "no_significant_difference"


async def test_regression_and_cost_quality_tradeoff(client, suite_and_runs):
    acct, _, make_run = suite_and_runs
    base = await make_run(
        "fake-model", {i: (1.0, True) for i in range(40)}, cost=0.002, latency=900.0
    )
    cand = await make_run(
        "cheap-model",
        {i: (1.0, True) if i >= 12 else (0.2, False) for i in range(40)},
        cost=0.0005,
        latency=300.0,
    )

    body = await _compare(client, acct, base, cand)

    assert body["verdict"] == "regressed"
    assert body["score"]["ci_high"] < 0
    assert body["pass_rate"]["regressions"] == 12
    assert body["cost"]["delta_pct"] == pytest.approx(-75.0)
    assert body["latency"]["delta_ms"] == pytest.approx(-600.0)
    # Biggest regressions first.
    assert body["cases"][0]["change"] == "regressed"
    assert body["cases"][0]["delta"] == pytest.approx(-0.8)
    assert body["candidate"]["model"] == "Fake/cheap-model"


async def test_repeats_are_averaged_per_case(client, suite_and_runs):
    acct, _, make_run = suite_and_runs
    base = await make_run("fake-model", {i: (1.0, True) for i in range(40)}, repeats=3)
    # Each case passes 1 of 3 repeats -> case fails, score 1/3.
    cand = await make_run(
        "fake-model",
        {i: (lambda r: (1.0, True) if r == 0 else (0.0, False)) for i in range(40)},
        repeats=3,
    )
    body = await _compare(client, acct, base, cand)
    assert body["cases"][0]["candidate_score"] == pytest.approx(1 / 3)
    assert body["cases"][0]["candidate_passed"] is False
    assert body["pass_rate"]["regressions"] == 40


async def test_only_shared_cases_are_compared(client, suite_and_runs):
    acct, _, make_run = suite_and_runs
    base = await make_run("fake-model", {i: (1.0, True) for i in range(30)})
    cand = await make_run("fake-model", {i: (1.0, True) for i in range(10, 40)})
    body = await _compare(client, acct, base, cand)
    assert body["paired_cases"] == 20
    assert body["baseline_only"][:2] == ["c00", "c01"]
    assert body["candidate_only"][-1] == "c39"


async def test_comparison_is_deterministic(client, suite_and_runs):
    acct, _, make_run = suite_and_runs
    base = await make_run("fake-model", {i: (i % 3 / 2, i % 3 == 2) for i in range(40)})
    cand = await make_run(
        "fake-model", {i: ((i + 1) % 3 / 2, (i + 1) % 3 == 2) for i in range(40)}
    )
    first = await _compare(client, acct, base, cand)
    second = await _compare(client, acct, base, cand)
    assert first["score"] == second["score"]


async def test_baseline_marking_and_default_comparison(client, suite_and_runs):
    acct, suite, make_run = suite_and_runs
    base = await make_run("fake-model", {i: (1.0, True) for i in range(40)})
    cand = await make_run("fake-model", {i: (1.0, True) for i in range(40)})

    resp = await client.get(
        "/evals/compare", params={"candidate": cand}, headers=acct.headers
    )
    assert resp.status_code == 400
    assert "no baseline" in resp.json()["error"]

    resp = await client.put(
        f"/evals/suites/{suite['id']}/baseline",
        json={"run_id": base},
        headers=acct.headers,
    )
    assert resp.json()["baseline_run_id"] == base

    body = (
        await client.get(
            "/evals/compare", params={"candidate": cand}, headers=acct.headers
        )
    ).json()
    assert body["baseline"]["id"] == base

    cleared = await client.put(
        f"/evals/suites/{suite['id']}/baseline",
        json={"run_id": None},
        headers=acct.headers,
    )
    assert cleared.json()["baseline_run_id"] is None


async def test_only_completed_runs_can_be_the_baseline(
    client, suite_and_runs, db_session
):
    acct, suite, make_run = suite_and_runs
    run_id = await make_run("fake-model", {0: (1.0, True)})
    run = await db_session.get(EvalRun, run_id)
    run.status = "running"
    await db_session.commit()
    resp = await client.put(
        f"/evals/suites/{suite['id']}/baseline",
        json={"run_id": run_id},
        headers=acct.headers,
    )
    assert resp.status_code == 400


async def test_comparing_across_suites_or_the_same_run_is_rejected(
    client, suite_and_runs
):
    acct, _, make_run = suite_and_runs
    run = await make_run("fake-model", {0: (1.0, True)})
    other_suite = (
        await client.post(
            "/evals/suites/import",
            json={"content": SUITE.replace("name: cmp", "name: other")},
            headers=acct.headers,
        )
    ).json()
    from llmwatch.db.engine import get_sessionmaker

    async with get_sessionmaker()() as session:
        (other,) = await create_runs(
            session,
            acct.workspace_id,
            suite_id=other_suite["id"],
            variants=[VariantSpec("fake-model")],
        )
        await session.commit()
        other_id = other.id
    for params in (
        {"baseline": run, "candidate": other_id},
        {"baseline": run, "candidate": run},
    ):
        resp = await client.get("/evals/compare", params=params, headers=acct.headers)
        assert resp.status_code == 400


async def test_compare_is_workspace_scoped(client, suite_and_runs, make_account):
    acct, _, make_run = suite_and_runs
    base = await make_run("fake-model", {0: (1.0, True)})
    cand = await make_run("fake-model", {0: (0.0, False)})
    other = await make_account(workspace="Other")
    resp = await client.get(
        "/evals/compare",
        params={"baseline": base, "candidate": cand},
        headers=other.headers,
    )
    assert resp.status_code == 404


async def test_tiny_samples_are_not_called_significant(client, suite_and_runs):
    """Regression: with 3 paired cases that all improved, the bootstrap interval
    collapsed to [+1, +1] and the comparison said "improved" although McNemar
    (p = 0.25) did not support it."""
    acct, _, make_run = suite_and_runs
    base = await make_run("fake-model", {i: (0.0, False) for i in range(3)})
    cand = await make_run("fake-model", {i: (1.0, True) for i in range(3)})

    body = await _compare(client, acct, base, cand)

    assert body["paired_cases"] == 3
    assert body["score"]["delta"] == pytest.approx(1.0)
    assert body["score"]["significant"] is False
    assert body["pass_rate"]["p_value"] == pytest.approx(0.25)
    assert body["verdict"] == "no_significant_difference"
    assert any("3 paired cases" in w for w in body["warnings"])


async def test_small_but_decisive_samples_can_still_be_significant(
    client, suite_and_runs
):
    """McNemar's exact test is valid for small n: 8 of 8 fixes is p = 2/256."""
    acct, _, make_run = suite_and_runs
    base = await make_run("fake-model", {i: (0.0, False) for i in range(8)})
    cand = await make_run("fake-model", {i: (1.0, True) for i in range(8)})
    body = await _compare(client, acct, base, cand)
    assert body["score"]["significant"] is False  # bootstrap needs >= 10 cases
    assert body["pass_rate"]["significant"] is True
    assert body["verdict"] == "improved"


async def test_enough_cases_have_no_warning(client, suite_and_runs):
    acct, _, make_run = suite_and_runs
    base = await make_run("fake-model", {i: (1.0, True) for i in range(40)})
    cand = await make_run("fake-model", {i: (1.0, True) for i in range(40)})
    assert (await _compare(client, acct, base, cand))["warnings"] == []
