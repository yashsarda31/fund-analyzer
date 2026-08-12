from __future__ import annotations

from datetime import datetime

from dateutil.parser import parse as parse_date

from ..models import PerformancePoint, ProductIdentity, ProductType, SourceResult
from .http import SafeHttpClient


NAV_ALL_URL = "https://www.amfiindia.com/spages/NAVAll.txt"


def _plan_option(name: str) -> tuple[str | None, str | None]:
    lower = name.lower()
    plan = "Direct" if "direct" in lower else "Regular" if "regular" in lower else None
    option = "Growth" if "growth" in lower else "Distribution" if any(token in lower for token in ("idcw", "dividend", "distribution")) else None
    return plan, option


def parse_amfi_directory(text: str, retrieved_at: datetime) -> list[ProductIdentity]:
    products: list[ProductIdentity] = []
    category = None
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if ";" not in line:
            if "(" in line and ")" in line:
                category = line[line.find("(") + 1:line.rfind(")")].strip()
            continue
        parts = [part.strip() for part in line.split(";")]
        if len(parts) < 6 or not parts[0].isdigit():
            continue
        plan, option = _plan_option(parts[3])
        provider = parts[3].split(" Mutual Fund")[0] if " Mutual Fund" in parts[3] else "AMFI registered mutual fund"
        products.append(ProductIdentity(product_type=ProductType.MUTUAL_FUND, name=parts[3], provider=provider, scheme_code=parts[0], plan=plan, option=option, category=category))
    return products


def parse_amfi_history(text: str, scheme_code: str, retrieved_at: datetime) -> list[PerformancePoint]:
    points: list[PerformancePoint] = []
    for line in text.splitlines():
        parts = [part.strip() for part in line.split(";")]
        if len(parts) < 6 or parts[0] != str(scheme_code):
            continue
        try:
            points.append(PerformancePoint(date=parse_date(parts[5], dayfirst=True).date(), value=float(parts[4]), series_kind="NAV"))
        except (ValueError, TypeError):
            continue
    return sorted({point.date: point for point in points}.values(), key=lambda point: point.date)


class AmfiCollector:
    def __init__(self, http: SafeHttpClient | None = None):
        self.http = http or SafeHttpClient()

    def directory(self) -> SourceResult:
        now = datetime.now().astimezone()
        response = self.http.get(NAV_ALL_URL, accepted_types={"text/plain"})
        products = parse_amfi_directory(response.text, now)
        return SourceResult(source_name="AMFI", available=True, products=products)

    def current_history(self, scheme_code: str) -> SourceResult:
        now = datetime.now().astimezone()
        response = self.http.get(NAV_ALL_URL, accepted_types={"text/plain"})
        points = parse_amfi_history(response.text, scheme_code, now)
        return SourceResult(source_name="AMFI", available=True, performance_points=points, warnings=[] if points else ["No current NAV found"])

