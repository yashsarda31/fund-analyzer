from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import pandas as pd
from pydantic import BaseModel, ConfigDict, Field

from .ai.validation import build_evidence_packet
from .analytics.private_markets import analyze_private_market_cash_flows
from .analytics.public_markets import calculate_public_metrics, growth_of_amount
from .models import AnalysisReport, AnalysisStatus, CashFlowKind, ChartSpec, EvidenceItem, EvidenceKind, Metric, PerformancePoint, PrivateMarketCashFlow, ProductIdentity, ProductType, SourceRef
from .pdf_extract import extract_pdf


class AnalysisRequest(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    identity: ProductIdentity
    public_url: str | None = None
    pdf_bytes: bytes | None = None
    benchmark_override: str | None = None
    cash_flows: list[PrivateMarketCashFlow] = Field(default_factory=list)


class Services(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)
    amfi: Any | None = None
    apmi: Any | None = None
    sebi: Any | None = None
    nifty: Any | None = None
    rbi: Any | None = None
    public_page: Any | None = None
    ai: Any | None = None


METRIC_LABELS = {
    "cagr_1y": "CAGR 1Y",
    "cagr_3y": "CAGR 3Y",
    "cagr_5y": "CAGR 5Y",
    "volatility": "Volatility (ann.)",
    "max_drawdown": "Max drawdown",
    "sharpe": "Sharpe ratio",
    "sortino": "Sortino ratio",
    "alpha": "Alpha (ann.)",
}


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

        benchmark_name = (request.benchmark_override or request.identity.benchmark or "").strip()
        benchmark_series: pd.Series | None = None
        if request.identity.product_type is ProductType.MUTUAL_FUND and points and benchmark_name and self.services.nifty:
            try:
                bench = self.services.nifty.tri_history(benchmark_name)
                if bench.available and bench.performance_points:
                    benchmark_series = pd.Series({pd.Timestamp(point.date): point.value for point in bench.performance_points}).sort_index()
                    last = bench.performance_points[-1]
                    evidence.append(EvidenceItem(
                        id="benchmark-series",
                        kind=EvidenceKind.VERIFIED_FACT,
                        label=f"Benchmark TRI series ({benchmark_name})",
                        value=last.value,
                        unit="index",
                        source=SourceRef(
                            title=f"NSE Total Returns Index: {benchmark_name}",
                            publisher="NSE",
                            url="https://www.niftyindices.com/",
                            observed_at=last.date,
                            retrieved_at=datetime.now(timezone.utc),
                        ),
                    ))
                else:
                    warnings.extend(bench.warnings or [f"Benchmark series unavailable: {bench.error_code}"])
            except Exception as exc:
                warnings.append(f"Benchmark series unavailable: {type(exc).__name__}")

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
        if request.identity.product_type is ProductType.AIF and request.cash_flows:
            try:
                analysis = analyze_private_market_cash_flows(request.cash_flows)
                retrieved = datetime.now(timezone.utc)
                input_ids: list[str] = []
                contribution_ids: list[str] = []
                distribution_ids: list[str] = []
                residual_ids: list[str] = []
                for index, flow in enumerate(request.cash_flows, 1):
                    item_id = f"user-cash-flow-{index}"
                    input_ids.append(item_id)
                    if flow.kind is CashFlowKind.CONTRIBUTION:
                        contribution_ids.append(item_id)
                    elif flow.kind is CashFlowKind.DISTRIBUTION:
                        distribution_ids.append(item_id)
                    else:
                        residual_ids.append(item_id)
                    evidence.append(EvidenceItem(
                        id=item_id,
                        kind=EvidenceKind.USER_INPUT,
                        label=f"{flow.kind.value} on {flow.date.isoformat()}",
                        value=flow.amount,
                        unit="INR",
                        source=SourceRef(
                            title="User-entered dated AIF cash flow",
                            publisher="User input",
                            observed_at=flow.date,
                            retrieved_at=retrieved,
                        ),
                        excerpt=flow.note,
                    ))
                metrics = [
                    Metric(key="xirr", label="XIRR", value=analysis.xirr, unit="%", period="Since first cash flow", as_of=analysis.as_of, source_ids=input_ids),
                    Metric(key="tvpi", label="TVPI", value=analysis.multiples.tvpi, unit="x", as_of=analysis.as_of, source_ids=input_ids),
                    Metric(key="dpi", label="DPI", value=analysis.multiples.dpi, unit="x", as_of=analysis.as_of, source_ids=[*contribution_ids, *distribution_ids]),
                    Metric(key="rvpi", label="RVPI", value=analysis.multiples.rvpi, unit="x", as_of=analysis.as_of, source_ids=[*contribution_ids, *residual_ids]),
                ]
                chart = ChartSpec(kind="cash_flow_timeline", product=[
                    PerformancePoint(
                        date=flow.date,
                        value=-flow.amount if flow.kind is CashFlowKind.CONTRIBUTION else flow.amount,
                        series_kind="valuation" if flow.kind is CashFlowKind.RESIDUAL_VALUE else "cash_flow",
                    )
                    for flow in request.cash_flows
                ])
                warnings.append("AIF calculations use user-entered cash flows. Verify every date and amount against capital-call, distribution, and valuation statements.")
            except ValueError as exc:
                warnings.append(f"AIF cash-flow calculation unavailable: {exc}")
        elif points:
            series = pd.Series({pd.Timestamp(point.date): point.value for point in points}).sort_index()
            bench_aligned: pd.Series | None = None
            if benchmark_series is not None:
                trimmed = benchmark_series[benchmark_series.index >= series.index.min()]
                bench_aligned = trimmed if not trimmed.empty else benchmark_series
            calculated = calculate_public_metrics(series, bench_aligned, None)
            metrics = [Metric(key=key, label=METRIC_LABELS.get(key, key.replace("_", " ").title()), value=value, unit="ratio" if key in {"sharpe", "sortino"} else "%", as_of=points[-1].date, warnings=calculated.warnings if key == "cagr_1y" else []) for key, value in calculated.values.items()]
            rebased = growth_of_amount(series)
            chart = ChartSpec(
                kind="growth_of_100k",
                product=[PerformancePoint(date=index.date(), value=float(value), series_kind="NAV") for index, value in rebased.items()],
                benchmark=[PerformancePoint(date=index.date(), value=float(value), series_kind="TRI") for index, value in growth_of_amount(bench_aligned).items()] if bench_aligned is not None else [],
            )
            now = datetime.now(timezone.utc)
            evidence.extend([
                EvidenceItem(id="performance-start", kind=EvidenceKind.VERIFIED_FACT, label="Performance series start", value=points[0].value, unit="NAV", source=SourceRef(title="AMFI NAV history", publisher="AMFI", url="https://www.amfiindia.com/net-asset-value", observed_at=points[0].date, retrieved_at=now)),
                EvidenceItem(id="performance-end", kind=EvidenceKind.VERIFIED_FACT, label="Latest NAV", value=points[-1].value, unit="NAV", source=SourceRef(title="AMFI NAV history", publisher="AMFI", url="https://www.amfiindia.com/net-asset-value", observed_at=points[-1].date, retrieved_at=now)),
            ])

        has_performance = bool(points) or bool(metrics) or any("return" in item.label.lower() or item.label in {"TVPI", "DPI", "IRR"} for item in evidence)
        benchmark_unavailable = request.identity.product_type is ProductType.MUTUAL_FUND and bool(benchmark_name) and benchmark_series is None
        if source_failed and not has_performance:
            status = AnalysisStatus.SOURCE_UNAVAILABLE
        elif not has_performance:
            status = AnalysisStatus.INSUFFICIENT
            warnings.append("Insufficient verified performance history")
        elif benchmark_unavailable or not benchmark_name:
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
