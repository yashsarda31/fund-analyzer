from datetime import date

import pytest
import pandas as pd

from fund_analyzer.cash_flow_input import parse_cash_flow_rows
from fund_analyzer.models import CashFlowKind


def test_cash_flow_rows_are_typed_and_blank_rows_are_ignored():
    rows = [
        {"date": "2023-01-01", "kind": "Contribution", "amount": 100.5, "note": "First close"},
        {"date": None, "kind": None, "amount": None, "note": None},
    ]

    parsed = parse_cash_flow_rows(rows)

    assert len(parsed) == 1
    assert parsed[0].date == date(2023, 1, 1)
    assert parsed[0].kind is CashFlowKind.CONTRIBUTION
    assert parsed[0].amount == 100.5


def test_cash_flow_rows_ignore_pandas_missing_values():
    assert parse_cash_flow_rows([{"date": pd.NaT, "kind": pd.NA, "amount": float("nan"), "note": pd.NA}]) == []


def test_cash_flow_rows_reject_incomplete_or_negative_entries():
    with pytest.raises(ValueError, match="Row 1.*date, type, and amount"):
        parse_cash_flow_rows([{"date": None, "kind": "Distribution", "amount": 10, "note": ""}])
    with pytest.raises(ValueError, match="Row 1.*positive amount"):
        parse_cash_flow_rows([{"date": "2024-01-01", "kind": "Contribution", "amount": -10, "note": ""}])
