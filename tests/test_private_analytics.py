from datetime import date

import pytest

from fund_analyzer.analytics.private_markets import private_market_multiples, xirr


def test_xirr_and_aif_multiples_use_dated_cash_flows():
    flows = [(date(2023, 1, 1), -100.0), (date(2026, 1, 1), 133.1)]
    assert xirr(flows) == pytest.approx(0.10, abs=2e-4)
    result = private_market_multiples(100, 40, 90)
    assert result.tvpi == 1.30
    assert result.dpi == 0.40


def test_xirr_requires_both_cash_flow_signs():
    with pytest.raises(ValueError, match="positive and one negative"):
        xirr([(date(2024, 1, 1), -100), (date(2025, 1, 1), -20)])
