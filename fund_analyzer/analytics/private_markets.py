from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from scipy.optimize import brentq


@dataclass(frozen=True)
class PrivateMarketMultiples:
    dpi: float
    rvpi: float
    tvpi: float
    moic: float


def xirr(cash_flows: list[tuple[date, float]]) -> float:
    if not cash_flows or not any(value > 0 for _, value in cash_flows) or not any(value < 0 for _, value in cash_flows):
        raise ValueError("XIRR requires at least one positive and one negative cash flow")
    ordered = sorted(cash_flows)
    origin = ordered[0][0]

    def npv(rate: float) -> float:
        return sum(value / ((1 + rate) ** ((day - origin).days / 365.2425)) for day, value in ordered)

    return float(brentq(npv, -0.9999, 1000))


def private_market_multiples(contributions: float, distributions: float, residual_value: float) -> PrivateMarketMultiples:
    if contributions <= 0:
        raise ValueError("Contributions must be positive")
    return PrivateMarketMultiples(
        dpi=distributions / contributions,
        rvpi=residual_value / contributions,
        tvpi=(distributions + residual_value) / contributions,
        moic=(distributions + residual_value) / contributions,
    )


def kaplan_schoar_pme(contributions: list[tuple[date, float]], distributions: list[tuple[date, float]], benchmark_values: dict[date, float], end_value: float) -> float:
    if not benchmark_values:
        raise ValueError("Benchmark values are required")
    end_date = max(benchmark_values)
    end_index = benchmark_values[end_date]
    scaled_contrib = sum(value * end_index / benchmark_values[day] for day, value in contributions)
    scaled_distrib = sum(value * end_index / benchmark_values[day] for day, value in distributions)
    return (scaled_distrib + end_value) / scaled_contrib
