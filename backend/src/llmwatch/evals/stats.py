"""
Module: stats.py (evals)
Purpose: Statistics for comparing two eval runs: is the difference real or noise?
WHY: "Candidate scored 0.82 vs 0.79" means little on 40 cases. Two complementary
tests, both paired (the same cases in both runs, so case difficulty cancels out):

  - Mean score delta: a paired bootstrap confidence interval. Resample the per-case
    score differences with replacement many times and take the percentile interval
    of their means. If the 95% interval excludes 0, the score change is significant.
  - Pass/fail: McNemar's test on the discordant cases only (b = passed before and
    failed now, c = failed before and passed now). Exact binomial test when b + c is
    small (< 25), otherwise the chi-squared test with continuity correction.
"""

import math
from dataclasses import dataclass

import numpy as np

DEFAULT_RESAMPLES = 10_000
DEFAULT_CONFIDENCE = 0.95
EXACT_MCNEMAR_BELOW = 25


@dataclass(frozen=True)
class BootstrapResult:
    mean: float
    low: float
    high: float
    confidence: float
    resamples: int

    @property
    def significant(self) -> bool:
        """The interval excludes zero."""
        return self.low > 0 or self.high < 0


def paired_bootstrap(
    deltas: list[float],
    *,
    resamples: int = DEFAULT_RESAMPLES,
    confidence: float = DEFAULT_CONFIDENCE,
    seed: int = 0,
) -> BootstrapResult:
    """Percentile bootstrap CI for the mean of paired differences.

    Seeded, so the same inputs always give the same interval.
    """
    if not deltas:
        raise ValueError("No paired cases to compare")
    data = np.asarray(deltas, dtype=float)
    mean = float(data.mean())
    if len(data) == 1:
        return BootstrapResult(mean, mean, mean, confidence, 0)
    rng = np.random.default_rng(seed)
    means = np.empty(resamples)
    # Chunked so memory stays bounded for large suites.
    chunk = max(1, min(resamples, 2_000_000 // len(data)))
    for start in range(0, resamples, chunk):
        size = min(chunk, resamples - start)
        idx = rng.integers(0, len(data), size=(size, len(data)))
        means[start : start + size] = data[idx].mean(axis=1)
    alpha = (1 - confidence) / 2
    low, high = np.quantile(means, [alpha, 1 - alpha])
    return BootstrapResult(mean, float(low), float(high), confidence, resamples)


@dataclass(frozen=True)
class McNemarResult:
    # Passed in the baseline, failed in the candidate (regressions).
    b: int
    # Failed in the baseline, passed in the candidate (fixes).
    c: int
    p_value: float
    test: str  # "exact" or "chi2_cc"; "none" when there are no discordant cases

    def significant(self, alpha: float = 0.05) -> bool:
        return self.p_value < alpha


def mcnemar(b: int, c: int) -> McNemarResult:
    """Two-sided McNemar test from the discordant counts."""
    n = b + c
    if n == 0:
        return McNemarResult(b, c, 1.0, "none")
    if n < EXACT_MCNEMAR_BELOW:
        k = min(b, c)
        tail = sum(math.comb(n, i) for i in range(k + 1)) / 2**n
        return McNemarResult(b, c, min(1.0, 2 * tail), "exact")
    statistic = (abs(b - c) - 1) ** 2 / n
    # Survival function of chi-squared with 1 degree of freedom.
    p = math.erfc(math.sqrt(statistic / 2))
    return McNemarResult(b, c, p, "chi2_cc")


def relative_change(new: float | None, old: float | None) -> float | None:
    """Percentage change, or None without a meaningful baseline."""
    if new is None or old is None or old == 0:
        return None
    return (new - old) / abs(old) * 100
