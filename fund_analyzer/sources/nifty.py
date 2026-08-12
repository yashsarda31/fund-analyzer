from __future__ import annotations

from datetime import datetime
from dateutil.parser import parse as parse_date

from ..models import PerformancePoint


def parse_nifty_tri(payload: dict, retrieved_at: datetime) -> list[PerformancePoint]:
    rows = payload.get("data") or payload.get("d") or []
    points: list[PerformancePoint] = []
    for row in rows:
        date_value = next((value for key, value in row.items() if key.lower() == "date"), None)
        tri_value = next((value for key, value in row.items() if "total return" in key.lower() and "net" not in key.lower()), None)
        if date_value is None or tri_value is None:
            continue
        try:
            points.append(PerformancePoint(date=parse_date(str(date_value), dayfirst=True).date(), value=float(str(tri_value).replace(",", "")), series_kind="TRI"))
        except ValueError:
            continue
    return sorted(points, key=lambda point: point.date)

