"""Drift between two windows of categorical values: Population Stability Index and Jensen-Shannon distance.

Both are among the drift metrics Azure Machine Learning model monitoring lists for categorical data. PSI bands follow
the guidance on Learn (Azure Databricks data profiling): < 0.1 no significant change, < 0.2 moderate, >= 0.2
significant. Small windows are reported as insufficient instead of guessed.
"""
from __future__ import annotations

import math
from collections import Counter
from dataclasses import dataclass, field

EPSILON = 1e-4          # smoothing for empty bins: a value never seen in the baseline would make PSI infinite
MIN_COUNT = 30          # fewer records than this in either window -> "insufficient", not a verdict
PSI_MODERATE = 0.1
PSI_SIGNIFICANT = 0.2


def distribution(counts: dict[str, int], categories: list[str]) -> list[float]:
    """Proportions over a fixed category list, with EPSILON for empty bins, renormalised to sum to 1."""
    total = sum(counts.get(c, 0) for c in categories)
    if total == 0:
        raise ValueError("no observations")
    raw = [max(counts.get(c, 0) / total, EPSILON) for c in categories]
    s = sum(raw)
    return [p / s for p in raw]


def psi(expected: list[float], actual: list[float]) -> float:
    """PSI = sum((actual - expected) * ln(actual / expected)); 0 when identical, grows with the shift."""
    return sum((a - e) * math.log(a / e) for e, a in zip(expected, actual))


def js_distance(p: list[float], q: list[float]) -> float:
    """Square root of the Jensen-Shannon divergence (log base 2): bounded between 0 and 1, symmetric."""
    m = [(a + b) / 2 for a, b in zip(p, q)]

    def kl(x, y):
        return sum(a * math.log2(a / b) for a, b in zip(x, y) if a > 0)

    return math.sqrt(max(0.0, (kl(p, m) + kl(q, m)) / 2))


@dataclass
class FeatureDrift:
    feature: str
    n_baseline: int
    n_current: int
    psi: float | None = None
    js: float | None = None
    status: str = "insufficient"               # ok | moderate | significant | insufficient
    shifts: list[tuple[str, float, float]] = field(default_factory=list)   # (value, baseline %, current %)

    @property
    def drifted(self) -> bool:
        return self.status == "significant"


def compare(feature: str, baseline: list[str], current: list[str], *, min_count: int = MIN_COUNT) -> FeatureDrift:
    b, c = Counter(baseline), Counter(current)
    result = FeatureDrift(feature, sum(b.values()), sum(c.values()))
    if result.n_baseline < min_count or result.n_current < min_count:
        return result
    cats = sorted(set(b) | set(c))
    p, q = distribution(b, cats), distribution(c, cats)
    result.psi, result.js = psi(p, q), js_distance(p, q)
    result.status = ("significant" if result.psi >= PSI_SIGNIFICANT
                     else "moderate" if result.psi >= PSI_MODERATE else "ok")
    shares = [(cat, b[cat] / result.n_baseline, c[cat] / result.n_current) for cat in cats]
    result.shifts = sorted(shares, key=lambda s: abs(s[2] - s[1]), reverse=True)[:3]
    return result
