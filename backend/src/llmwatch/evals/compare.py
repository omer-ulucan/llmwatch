"""
Module: compare.py (evals)
Purpose: Compares a candidate run against a baseline run of the same suite.
WHY: The question an eval should answer is "did this change make things better, and
by more than noise?", with cost next to quality. Cases are paired by their stable id
(so suites can evolve between versions; unpaired cases are reported, not compared).
Repeats are averaged per case first: a case passes when at least half its repeats
pass, and its score is the mean over repeats.
"""

from collections import defaultdict
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from llmwatch.db.models import EvalCase, EvalResult, EvalRun
from llmwatch.evals.stats import mcnemar, paired_bootstrap, relative_change
from llmwatch.exceptions import ResourceNotFoundException, ValidationException

ALPHA = 0.05
# WHY: Percentile bootstrap intervals under-cover on tiny samples (with 3 cases that
# all moved the same way the interval collapses to a single point), so the bootstrap
# never declares significance below this. McNemar's exact test stays valid and can
# still decide on its own.
MIN_PAIRED_FOR_BOOTSTRAP = 10


@dataclass
class CaseSummary:
    score: float
    passed: bool
    cost: float
    latency: float
    errors: int
    repeats: int


async def _load(session: AsyncSession, workspace_id: str, run_id: str) -> EvalRun:
    run = (
        await session.execute(
            select(EvalRun).where(
                EvalRun.id == run_id, EvalRun.workspace_id == workspace_id
            )
        )
    ).scalar_one_or_none()
    if run is None:
        raise ResourceNotFoundException(f"Run {run_id} not found")
    return run


async def _case_summaries(session: AsyncSession, run_id: str) -> dict[str, CaseSummary]:
    rows = (
        await session.execute(
            select(EvalCase.case_key, EvalResult)
            .join(EvalCase, EvalCase.id == EvalResult.case_id)
            .where(EvalResult.run_id == run_id)
        )
    ).all()
    grouped: dict[str, list[EvalResult]] = defaultdict(list)
    for key, result in rows:
        grouped[key].append(result)
    out = {}
    for key, results in grouped.items():
        n = len(results)
        out[key] = CaseSummary(
            score=sum(r.score for r in results) / n,
            passed=sum(1 for r in results if r.passed) * 2 >= n,
            cost=sum(r.cost_usd for r in results) / n,
            latency=sum(r.latency_ms for r in results) / n,
            errors=sum(1 for r in results if r.error),
            repeats=n,
        )
    return out


def _run_info(run: EvalRun) -> dict[str, Any]:
    return {
        "id": run.id,
        "label": run.label,
        "status": run.status,
        "model": run.variant.get("model_label"),
        "params": run.variant.get("params", {}),
        "suite_version_id": run.suite_version_id,
        "repeats": run.repeats,
        "mean_score": run.mean_score,
        "pass_rate": run.pass_rate,
        "total_cost_usd": run.total_cost_usd,
        "created_at": run.created_at.isoformat(),
    }


def _priced(run: EvalRun) -> bool:
    snap = run.pricing_snapshot or {}
    return (
        snap.get("input_price_per_mtok") is not None
        or snap.get("output_price_per_mtok") is not None
    )


def _mean(values: list[float]) -> float | None:
    return sum(values) / len(values) if values else None


async def compare_runs(
    session: AsyncSession,
    workspace_id: str,
    baseline_id: str,
    candidate_id: str,
    *,
    seed: int = 0,
    resamples: int = 10_000,
) -> dict[str, Any]:
    baseline = await _load(session, workspace_id, baseline_id)
    candidate = await _load(session, workspace_id, candidate_id)
    if baseline.suite_id != candidate.suite_id:
        raise ValidationException("Both runs must belong to the same suite")
    if baseline.id == candidate.id:
        raise ValidationException("Pick two different runs")

    base_cases = await _case_summaries(session, baseline.id)
    cand_cases = await _case_summaries(session, candidate.id)
    paired = sorted(set(base_cases) & set(cand_cases))
    if not paired:
        raise ValidationException("The runs have no cases in common to compare")

    deltas = [cand_cases[k].score - base_cases[k].score for k in paired]
    boot = paired_bootstrap(deltas, seed=seed, resamples=resamples)

    regressions = [
        k for k in paired if base_cases[k].passed and not cand_cases[k].passed
    ]
    fixes = [k for k in paired if not base_cases[k].passed and cand_cases[k].passed]
    test = mcnemar(len(regressions), len(fixes))

    base_pass = sum(base_cases[k].passed for k in paired) / len(paired)
    cand_pass = sum(cand_cases[k].passed for k in paired) / len(paired)
    base_cost = _mean([base_cases[k].cost for k in paired])
    cand_cost = _mean([cand_cases[k].cost for k in paired])
    base_lat = _mean([base_cases[k].latency for k in paired])
    cand_lat = _mean([cand_cases[k].latency for k in paired])

    warnings: list[str] = []
    score_significant = boot.significant and len(paired) >= MIN_PAIRED_FOR_BOOTSTRAP
    if len(paired) < MIN_PAIRED_FOR_BOOTSTRAP:
        warnings.append(
            f"Only {len(paired)} paired cases: the score interval is unreliable below "
            f"{MIN_PAIRED_FOR_BOOTSTRAP}, so only the pass/fail test can show "
            "significance. Add cases (or repeats) for a firmer answer."
        )
    if not (_priced(baseline) and _priced(candidate)):
        warnings.append(
            "At least one run's model is unpriced; cost deltas are incomplete."
        )

    if score_significant:
        verdict = "improved" if boot.mean > 0 else "regressed"
    elif test.significant(ALPHA):
        verdict = "improved" if len(fixes) > len(regressions) else "regressed"
    else:
        verdict = "no_significant_difference"

    cases = []
    for k in paired:
        b, c = base_cases[k], cand_cases[k]
        change = (
            "fixed" if k in fixes else "regressed" if k in regressions else "unchanged"
        )
        cases.append(
            {
                "case_id": k,
                "baseline_score": round(b.score, 6),
                "candidate_score": round(c.score, 6),
                "delta": round(c.score - b.score, 6),
                "baseline_passed": b.passed,
                "candidate_passed": c.passed,
                "change": change,
                "baseline_errors": b.errors,
                "candidate_errors": c.errors,
            }
        )
    # Biggest regressions first, then biggest improvements.
    cases.sort(key=lambda row: (row["delta"], row["case_id"]))

    return {
        "baseline": _run_info(baseline),
        "candidate": _run_info(candidate),
        "same_suite_version": baseline.suite_version_id == candidate.suite_version_id,
        "paired_cases": len(paired),
        "baseline_only": sorted(set(base_cases) - set(cand_cases)),
        "candidate_only": sorted(set(cand_cases) - set(base_cases)),
        "score": {
            "baseline_mean": _mean([base_cases[k].score for k in paired]),
            "candidate_mean": _mean([cand_cases[k].score for k in paired]),
            "delta": boot.mean,
            "ci_low": boot.low,
            "ci_high": boot.high,
            "confidence": boot.confidence,
            "resamples": boot.resamples,
            "significant": score_significant,
            "method": "paired bootstrap (percentile)",
        },
        "pass_rate": {
            "baseline": base_pass,
            "candidate": cand_pass,
            "delta": cand_pass - base_pass,
            "regressions": test.b,
            "fixes": test.c,
            "p_value": test.p_value,
            "test": test.test,
            "significant": test.significant(ALPHA),
            "alpha": ALPHA,
        },
        "cost": {
            "baseline_per_case": base_cost,
            "candidate_per_case": cand_cost,
            "delta_per_case": (cand_cost or 0) - (base_cost or 0),
            "delta_pct": relative_change(cand_cost, base_cost),
            "baseline_priced": _priced(baseline),
            "candidate_priced": _priced(candidate),
        },
        "latency": {
            "baseline_mean_ms": base_lat,
            "candidate_mean_ms": cand_lat,
            "delta_ms": (cand_lat or 0) - (base_lat or 0),
            "delta_pct": relative_change(cand_lat, base_lat),
        },
        "verdict": verdict,
        "warnings": warnings,
        "cases": cases,
    }
