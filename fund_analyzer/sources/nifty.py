from __future__ import annotations

import json
from datetime import datetime, timedelta

from dateutil.parser import parse as parse_date

from ..models import PerformancePoint, SourceResult
from .http import SafeHttpClient


def parse_nifty_tri(payload: dict | list, retrieved_at: datetime) -> list[PerformancePoint]:
    rows = payload if isinstance(payload, list) else (payload.get("data") or payload.get("d") or [])
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


TRI_URL = "https://www.niftyindices.com/Backpage.aspx/getTriData"

NIFTY_INDEX_NAMES = {
    "Nifty 500 TRI": "NIFTY 500",
    "Nifty 50 TRI": "NIFTY 50",
    "Nifty 100 TRI": "NIFTY 100",
    "Nifty 200 TRI": "NIFTY 200",
    "Nifty Midcap 150 TRI": "NIFTY MIDCAP 150",
    "Nifty Smallcap 250 TRI": "NIFTY SMALLCAP 250",
    "Nifty Next 50 TRI": "NIFTY NEXT 50",
}


def resolve_nifty_index(benchmark_name: str) -> str:
    normalized = " ".join(benchmark_name.strip().lower().split())
    for label, index_name in NIFTY_INDEX_NAMES.items():
        if normalized == label.lower():
            return index_name
    cleaned = normalized.replace(" tri", "").strip().upper()
    return cleaned or "NIFTY 500"


class NiftyCollector:
    """Fetches NSE Total Returns Index history for benchmark comparison.

    A missing or changed upstream service is reported as unavailable rather
    than silently substituted, matching the project's evidence rules.
    """

    def __init__(self, http: SafeHttpClient | None = None):
        self.http = http or SafeHttpClient()

    def tri_history(self, benchmark_name: str) -> SourceResult:
        index_name = resolve_nifty_index(benchmark_name)
        now = datetime.now().astimezone()
        payload = {
            "name": index_name,
            "startDate": (now - timedelta(days=3650)).strftime("%d-%b-%Y"),
            "endDate": now.strftime("%d-%b-%Y"),
            "yieldFlag": "1",
            "type": "TRI",
        }
        try:
            response = self.http.post_json(
                TRI_URL,
                payload=payload,
                headers={"Referer": "https://www.niftyindices.com/", "X-Requested-With": "XMLHttpRequest"},
            )
            raw = response.json()
        except Exception as exc:
            return SourceResult(source_name="NSE", available=False, error_code=type(exc).__name__, warnings=[f"NSE TRI request failed: {type(exc).__name__}"])
        data = raw.get("d", raw) if isinstance(raw, dict) else raw
        if isinstance(data, str):
            try:
                data = json.loads(data)
            except ValueError:
                return SourceResult(source_name="NSE", available=False, error_code="bad_payload")
        if isinstance(data, list):
            data = {"data": data}
        points = parse_nifty_tri(data if isinstance(data, dict) else {}, now)
        if not points:
            return SourceResult(source_name="NSE", available=False, error_code="no_data", warnings=[f"NSE returned no TRI rows for {index_name}"])
        return SourceResult(source_name="NSE", available=True, performance_points=points, warnings=[f"Benchmark index TRI from NSE: {index_name}"])

