from __future__ import annotations

from datetime import date, datetime
from typing import Any, Iterable, Mapping

import pandas as pd

from .models import CashFlowKind, PrivateMarketCashFlow


def _is_blank(value: Any) -> bool:
    if value is None:
        return True
    missing = pd.isna(value)
    if isinstance(missing, bool) and missing:
        return True
    return isinstance(value, str) and not value.strip()


def _as_date(value: Any) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return pd.Timestamp(value).date()


def parse_cash_flow_rows(rows: Iterable[Mapping[str, Any]]) -> list[PrivateMarketCashFlow]:
    parsed: list[PrivateMarketCashFlow] = []
    for row_number, row in enumerate(rows, 1):
        values = (row.get("date"), row.get("kind"), row.get("amount"), row.get("note"))
        if all(_is_blank(value) for value in values):
            continue
        if any(_is_blank(value) for value in values[:3]):
            raise ValueError(f"Row {row_number} requires a date, type, and amount")
        try:
            amount = float(row["amount"])
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Row {row_number} requires a numeric positive amount") from exc
        if amount < 0:
            raise ValueError(f"Row {row_number} requires a positive amount; the event type sets its cash-flow sign")
        try:
            parsed.append(PrivateMarketCashFlow(
                date=_as_date(row["date"]),
                kind=CashFlowKind(row["kind"]),
                amount=amount,
                note=None if _is_blank(row.get("note")) else str(row["note"]).strip(),
            ))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"Row {row_number} has an invalid date or cash-flow type") from exc
    return parsed
