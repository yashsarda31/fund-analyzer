from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from scipy.optimize import brentq

from ..models import CashFlowKind, PrivateMarketCashFlow


@dataclass(frozen=True)
class PrivateMarketMultiples:
    dpi: float
    rvpi: float
    tvpi: float
    moic: float


@dataclass(frozen=True)
class PrivateMarketAnalysis:
    xirr: float
    multiples: PrivateMarketMultiples
    contributions: float
    distributions: float
    residual_value: float
    as_of: date
    signed_cash_flows: list[tuple[date, float]]


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


def analyze_private_market_cash_flows(cash_flows: list[PrivateMarketCashFlow]) -> PrivateMarketAnalysis:
    if not cash_flows:
        raise ValueError("Dated cash flows are required")
    residuals = [flow for flow in cash_flows if flow.kind is CashFlowKind.RESIDUAL_VALUE]
    if len(residuals) != 1:
        raise ValueError("Dated cash flows require exactly one residual value, including zero for a fully realized fund")
    residual = residuals[0]
    if residual.date != max(flow.date for flow in cash_flows):
        raise ValueError("The residual value must be the latest dated entry")

    contributions = sum(flow.amount for flow in cash_flows if flow.kind is CashFlowKind.CONTRIBUTION)
    distributions = sum(flow.amount for flow in cash_flows if flow.kind is CashFlowKind.DISTRIBUTION)
    multiples = private_market_multiples(contributions, distributions, residual.amount)
    signed = [
        (flow.date, -flow.amount if flow.kind is CashFlowKind.CONTRIBUTION else flow.amount)
        for flow in cash_flows
    ]
    return PrivateMarketAnalysis(
        xirr=xirr(signed),
        multiples=multiples,
        contributions=contributions,
        distributions=distributions,
        residual_value=residual.amount,
        as_of=residual.date,
        signed_cash_flows=signed,
    )


def kaplan_schoar_pme(contributions: list[tuple[date, float]], distributions: list[tuple[date, float]], benchmark_values: dict[date, float], end_value: float) -> float:
    if not benchmark_values:
        raise ValueError("Benchmark values are required")
    end_date = max(benchmark_values)
    end_index = benchmark_values[end_date]
    scaled_contrib = sum(value * end_index / benchmark_values[day] for day, value in contributions)
    scaled_distrib = sum(value * end_index / benchmark_values[day] for day, value in distributions)
    return (scaled_distrib + end_value) / scaled_contrib
