"""Statistics for the study (S5, FR-S5; SPECIFICATION.md §6).

Every rate is a binomial proportion from finite yes/no trials, so it is reported
with an exact Clopper-Pearson 95% confidence interval. Decision rule: if two
conditions' CIs do not overlap the difference is real; if they overlap, report
inconclusive rather than over-claim.

The Clopper-Pearson bounds are quantiles of a Beta distribution. To avoid a hard
SciPy dependency for this core function, the regularized incomplete beta and its
inverse are implemented directly (Numerical-Recipes continued fraction + bisection).
"""

from __future__ import annotations

import math
from dataclasses import dataclass


def _betacf(a: float, b: float, x: float) -> float:
    """Continued fraction for the incomplete beta function."""
    tiny = 1e-30
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c = 1.0
    d = 1.0 - qab * x / qap
    if abs(d) < tiny:
        d = tiny
    d = 1.0 / d
    h = d
    for m in range(1, 300):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < tiny:
            d = tiny
        c = 1.0 + aa / c
        if abs(c) < tiny:
            c = tiny
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < 1e-12:
            break
    return h


def betainc(a: float, b: float, x: float) -> float:
    """Regularized incomplete beta function I_x(a, b)."""
    if x <= 0.0:
        return 0.0
    if x >= 1.0:
        return 1.0
    lbeta = math.lgamma(a + b) - math.lgamma(a) - math.lgamma(b)
    front = math.exp(lbeta + a * math.log(x) + b * math.log(1.0 - x))
    if x < (a + 1.0) / (a + b + 2.0):
        return front * _betacf(a, b, x) / a
    return 1.0 - front * _betacf(b, a, 1.0 - x) / b


def betaincinv(a: float, b: float, p: float) -> float:
    """Inverse of I_x(a, b) in x via bisection. p in [0, 1]."""
    if p <= 0.0:
        return 0.0
    if p >= 1.0:
        return 1.0
    lo, hi = 0.0, 1.0
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if betainc(a, b, mid) < p:
            lo = mid
        else:
            hi = mid
    return 0.5 * (lo + hi)


@dataclass(frozen=True)
class Rate:
    """A proportion with an exact binomial confidence interval."""

    successes: int
    n: int
    lo: float
    hi: float
    alpha: float = 0.05

    @property
    def point(self) -> float:
        return self.successes / self.n if self.n else 0.0

    def overlaps(self, other: "Rate") -> bool:
        return not (self.hi < other.lo or other.hi < self.lo)

    def __str__(self) -> str:
        return f"{self.point:.3f} [{self.lo:.3f}, {self.hi:.3f}] (n={self.n})"


def clopper_pearson(successes: int, n: int, alpha: float = 0.05) -> Rate:
    """Exact Clopper-Pearson interval for a binomial proportion."""
    if n < 0 or successes < 0 or successes > n:
        raise ValueError("require 0 <= successes <= n")
    if n == 0:
        return Rate(0, 0, 0.0, 1.0, alpha)
    lo = 0.0 if successes == 0 else betaincinv(successes, n - successes + 1, alpha / 2)
    hi = 1.0 if successes == n else betaincinv(successes + 1, n - successes, 1 - alpha / 2)
    return Rate(successes, n, lo, hi, alpha)
