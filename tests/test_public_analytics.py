from datetime import date, timedelta

import pandas as pd
import pytest

from fund_analyzer.analytics.public_markets import calculate_max_drawdown, calculate_public_metrics, growth_of_amount


def series(values, spacing=1):
    return pd.Series(values, index=pd.to_datetime([date(2023, 1, 1) + timedelta(days=i * spacing) for i in range(len(values))]))


def test_max_drawdown_uses_peak_to_trough():
    assert calculate_max_drawdown(series([100, 120, 90, 108])) == pytest.approx(-0.25)


def test_metrics_are_suppressed_when_history_is_sparse():
    result = calculate_public_metrics(series([100 + i for i in range(8)], 30), None, 0.065)
    assert result.values["cagr_1y"] is None
    assert any("1-year coverage" in warning for warning in result.warnings)


def test_growth_rebases_first_value():
    rebased = growth_of_amount(series([10, 11, 12]), 100_000)
    assert rebased.iloc[0] == 100_000
    assert rebased.iloc[-1] == 120_000

