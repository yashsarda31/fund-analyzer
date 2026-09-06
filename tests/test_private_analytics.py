from datetime import date

import pytest

from fund_analyzer.analytics.private_markets import (
    analyze_private_market_cash_flows,
    kaplan_schoar_pme,
    private_market_multiples,
    xirr,
)
from fund_analyzer.models import CashFlowKind, PrivateMarketCashFlow


def test_xirr_and_aif_multiples_use_dated_cash_flows():
    flows = [(date(2023, 1, 1), -100.0), (date(2026, 1, 1), 133.1)]
    assert xirr(flows) == pytest.approx(0.10, abs=2e-4)
    result = private_market_multiples(100, 40, 90)
    assert result.tvpi == 1.30
    assert result.dpi == 0.40


def test_xirr_requires_both_cash_flow_signs():
    with pytest.raises(ValueError, match="positive and one negative"):
        xirr([(date(2024, 1, 1), -100), (date(2025, 1, 1), -20)])


def test_pme_scales_flows_to_end_index():
    benchmark = {date(2024, 1, 1): 100, date(2025, 1, 1): 120}
    assert kaplan_schoar_pme([(date(2024, 1, 1), 100)], [(date(2025, 1, 1), 30)], benchmark, 90) == pytest.approx(1.0)


def test_private_market_input_validation():
    with pytest.raises(ValueError, match="positive"):
        private_market_multiples(0, 1, 1)
    with pytest.raises(ValueError, match="Benchmark"):
        kaplan_schoar_pme([], [], {}, 0)


def test_structured_cash_flows_calculate_xirr_and_all_aif_multiples():
    flows = [
        PrivateMarketCashFlow(date=date(2023, 1, 1), kind=CashFlowKind.CONTRIBUTION, amount=100),
        PrivateMarketCashFlow(date=date(2024, 1, 1), kind=CashFlowKind.DISTRIBUTION, amount=20),
        PrivateMarketCashFlow(date=date(2026, 1, 1), kind=CashFlowKind.RESIDUAL_VALUE, amount=110),
    ]

    result = analyze_private_market_cash_flows(flows)

    assert result.xirr == pytest.approx(xirr([(date(2023, 1, 1), -100), (date(2024, 1, 1), 20), (date(2026, 1, 1), 110)]))
    assert result.contributions == 100
    assert result.distributions == 20
    assert result.residual_value == 110
    assert result.multiples.dpi == pytest.approx(0.2)
    assert result.multiples.rvpi == pytest.approx(1.1)
    assert result.multiples.tvpi == pytest.approx(1.3)
    assert result.as_of == date(2026, 1, 1)


def test_structured_cash_flows_require_one_terminal_residual_value():
    missing_residual = [
        PrivateMarketCashFlow(date=date(2023, 1, 1), kind=CashFlowKind.CONTRIBUTION, amount=100),
        PrivateMarketCashFlow(date=date(2024, 1, 1), kind=CashFlowKind.DISTRIBUTION, amount=20),
    ]
    with pytest.raises(ValueError, match="exactly one residual value"):
        analyze_private_market_cash_flows(missing_residual)

    non_terminal_residual = [
        PrivateMarketCashFlow(date=date(2023, 1, 1), kind=CashFlowKind.CONTRIBUTION, amount=100),
        PrivateMarketCashFlow(date=date(2024, 1, 1), kind=CashFlowKind.RESIDUAL_VALUE, amount=80),
        PrivateMarketCashFlow(date=date(2025, 1, 1), kind=CashFlowKind.DISTRIBUTION, amount=20),
    ]
    with pytest.raises(ValueError, match="latest dated entry"):
        analyze_private_market_cash_flows(non_terminal_residual)
