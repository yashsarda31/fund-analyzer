from __future__ import annotations

from datetime import datetime
from io import StringIO
import re

import pandas as pd

from .http import SafeHttpClient


APMI_URL = "https://www.apmiindia.org/apmi/welcomeiaperformance.htm?action=PMSmenu"


def _number(value):
    text = re.sub(r"[^0-9.\-]", "", str(value))
    return float(text) if text and str(value).strip().upper() not in {"NA", "NAN", "-"} else None


def parse_apmi_performance(html: str, retrieved_at: datetime) -> list[dict]:
    tables = pd.read_html(StringIO(html))
    table = next((frame for frame in tables if any("IA Name" in str(column) for column in frame.columns)), pd.DataFrame())
    rows: list[dict] = []
    for _, row in table.iterrows():
        columns = {str(key).strip(): value for key, value in row.items()}
        def find(name):
            return next((value for key, value in columns.items() if name.lower() in key.lower()), None)
        returns = {key: _number(find(label)) for key, label in (("1m", "1 Month"), ("3m", "3 Month"), ("6m", "6 Month"), ("1y", "1 Year"), ("2y", "2 Year"), ("3y", "3 Year"), ("4y", "4 Year"), ("5y", "5 Year"), ("since_inception", "Since"))}
        rows.append({"provider": str(find("PMS Provider") or "").strip(), "approach": str(find("IA Name") or "").strip(), "aum_crore": _number(find("AUM")), "returns": returns})
    return rows


class ApmiCollector:
    def __init__(self, http: SafeHttpClient | None = None):
        self.http = http or SafeHttpClient()

    def performance(self) -> list[dict]:
        response = self.http.get(APMI_URL, accepted_types={"text/html"}, max_bytes=30_000_000)
        return parse_apmi_performance(response.text, datetime.now().astimezone())
