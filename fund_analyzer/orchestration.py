from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict

from .ai.validation import build_evidence_packet
from .analytics.public_markets import calculate_public_metrics, growth_of_amount
from .models import AnalysisReport, AnalysisStatus, ChartSpec, EvidenceItem, EvidenceKind, Metric, PerformancePoint, ProductIdentity, ProductType, SourceRef
from .pdf_extract import extract_pdf


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    identity: ProductIdentity
    public_url: str | None = None
    pdf_bytes: bytes | None = None
    benchmark_override: str | None = None


class Services(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    amfi: Any | None = None
    apmi: Any | None = None
    sebi: Any | None = None
    nifty: Any | None = None
    rbi: Any | None = None
    public_page: Any | None = None
    ai: Any | None = None


class FundAnalyzer:
    def __init__(self, services: Services):
        self.services = services

    def analyze(self, request: AnalysisRequest) -> AnalysisReport:
        evidence: list[EvidenceItem] = []
        warnings: list[str] = []
        metrics: list[Metric] = []
        points: list[PerformancePoint] = []
        source_failed = False

        if request.identity.product_type is ProductType.MUTUAL_FUND and self.services.amfi and request.identity.scheme_code:
            try:
                source = self.services.amfi.current_history(request.identity.scheme_code)
                source_failed = not source.available
                points.extend(source.performance_points)
                evidence.extend(source.evidence)
                warnings.extend(source.warnings)
            except Exception as exc:
                source_failed = True
                warnings.append(f"AMFI source unavailable: {type(exc).__name__}")
        elif request.identity.product_type is ProductType.PMS and self.services.apmi:
            try:
                rows = self.services.apmi.performance()
                row = next((item for item in rows if request.identity.name.lower() in item["approach"].lower()), None)
                if row:
                    now = datetime.now(timezone.utc)
                    source = SourceRef(title="APMI IA Performance", publisher="APMI", url="https://www.apmiindia.org/apmi/welcomeiaperformance.htm?action=PMSmenu", observed_at=now.date(), retrieved_at=now)
                    for period, value in row["returns"].items():
                        if value is not None:
                            evidence.append(EvidenceItem(id=f"apmi-return-{period}", kind=EvidenceKind.VERIFIED_FACT, label=f"Reported {period} return", value=value, unit="%", source=source))
            except Exception as exc:
                source_failed = True
                warnings.append(f"APMI source unavailable: {type(exc).__name__}")

        if request.public_url and self.services.public_page:
            try:
                result = self.services.public_page.extract(request.public_url, request.identity)
                evidence.extend(result.evidence)
                warnings.extend(result.warnings)
            except Exception as exc:
                warnings.append(f"Public URL unavailable: {type(exc).__name__}")

        if request.pdf_bytes:
            pdf = extract_pdf(request.pdf_bytes, request.identity)
            evidence.extend(pdf.evidence)
            warnings.extend(pdf.warnings)

        chart = None
        if points:
            series = pd.Series({pd.Timestamp(point.date): point.value for point in points}).sort_index()
            calculated = calculate_public_metrics(series, None, None)
            metrics = [Metric(key=key, label=key.replace("_", " ").title(), value=value, unit="ratio" if key in {"sharpe", "sortino"} else "%" if value is not None else "", as_of=points[-1].date, warnings=calculated.warnings if key == "cagr_1y" else []) for key, value in calculated.values.items()]
            rebased = growth_of_amount(series)
            chart = ChartSpec(kind="growth_of_100k", product=[PerformancePoint(date=index.date(), value=float(value), series_kind="NAV") for index, value in rebased.items()])
            now = datetime.now(timezone.utc)
            evidence.extend([
                EvidenceItem(id="performance-start", kind=EvidenceKind.VERIFIED_FACT, label="Performance series start", value=points[0].value, unit="NAV", source=SourceRef(title="AMFI NAV history", publisher="AMFI", url="https://www.amfiindia.com/net-asset-value", observed_at=points[0].date, retrieved_at=now)),
                EvidenceItem(id="performance-end", kind=EvidenceKind.VERIFIED_FACT, label="Latest NAV", value=points[-1].value, unit="NAV", source=SourceRef(title="AMFI NAV history", publisher="AMFI", url="https://www.amfiindia.com/net-asset-value", observed_at=points[-1].date, retrieved_at=now)),
            ])

        has_performance = bool(points) or any("return" in item.label.lower() or item.label in {"TVPI", "DPI", "IRR"} for item in evidence)
        if source_failed and not has_performance:
            status = AnalysisStatus.SOURCE_UNAVAILABLE
        elif not has_performance:
            status = AnalysisStatus.INSUFFICIENT
            warnings.append("Insufficient verified performance history")
        elif not request.identity.benchmark and not request.benchmark_override:
            status = AnalysisStatus.PARTIAL
            warnings.append("Benchmark comparison is unavailable")
        else:
            status = AnalysisStatus.COMPLETE

        ai = None
        if self.services.ai and evidence:
            packet = build_evidence_packet(request.identity, evidence, warnings, metrics)
            ai = self.services.ai.analyze(packet)
            if not ai.available:
                warnings.extend(ai.limitations)
        return AnalysisReport(identity=request.identity, status=status, evidence=evidence, metrics=metrics, ai=ai, chart=chart, warnings=list(dict.fromkeys(warnings)))
