"""Pure deterministic financial math.

No LLM, no I/O, no side effects — just auditable arithmetic that is unit-tested
and reused by the fact-aware tools. Invalid inputs raise ``ValueError`` so the
caller can surface a clean error instead of a wrong number.
"""
from __future__ import annotations

from typing import Sequence


def yoy_growth(begin: float, end: float) -> float:
    """Period-over-period growth: (end - begin) / |begin|."""
    if begin == 0:
        raise ValueError("growth undefined when the base value is zero")
    return (end - begin) / abs(begin)


def cagr(begin: float, end: float, years: float) -> float:
    """Compound annual growth rate: (end/begin)^(1/years) - 1."""
    if years <= 0:
        raise ValueError("years must be positive")
    if begin <= 0 or end <= 0:
        raise ValueError("CAGR requires positive begin and end values")
    return (end / begin) ** (1.0 / years) - 1.0


def margin(part: float, whole: float) -> float:
    """A margin/share: part / whole."""
    if whole == 0:
        raise ValueError("margin undefined when the denominator is zero")
    return part / whole


def ratio(numerator: float, denominator: float) -> float:
    if denominator == 0:
        raise ValueError("ratio undefined when the denominator is zero")
    return numerator / denominator


def project(base: float, growth_rate: float, years: int) -> list[float]:
    """Project ``base`` forward ``years`` periods at a constant growth rate."""
    if years < 0:
        raise ValueError("years must be non-negative")
    return [base * (1.0 + growth_rate) ** t for t in range(1, years + 1)]


def npv(rate: float, cashflows: Sequence[float]) -> float:
    """Net present value; cashflows[0] occurs at t=0 (undiscounted)."""
    if rate <= -1.0:
        raise ValueError("rate must be greater than -100%")
    return sum(cf / (1.0 + rate) ** t for t, cf in enumerate(cashflows))


def irr(
    cashflows: Sequence[float],
    lo: float = -0.9999,
    hi: float = 10.0,
    tol: float = 1e-7,
    max_iter: int = 200,
) -> float:
    """Internal rate of return via bracketed bisection on NPV(rate)."""
    if len(cashflows) < 2:
        raise ValueError("IRR needs at least two cashflows")
    f_lo = npv(lo, cashflows)
    f_hi = npv(hi, cashflows)
    if f_lo == 0:
        return lo
    if f_hi == 0:
        return hi
    if (f_lo > 0) == (f_hi > 0):
        raise ValueError("IRR not bracketed in [-99.99%, 1000%]; cashflows may lack a sign change")
    for _ in range(max_iter):
        mid = (lo + hi) / 2.0
        f_mid = npv(mid, cashflows)
        if abs(f_mid) < tol:
            return mid
        if (f_mid > 0) == (f_lo > 0):
            lo, f_lo = mid, f_mid
        else:
            hi, f_hi = mid, f_mid
    return (lo + hi) / 2.0
