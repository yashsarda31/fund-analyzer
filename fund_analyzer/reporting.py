from __future__ import annotations

from datetime import timedelta

from pydantic import BaseModel

from .models import AnalysisReport, ChartSpec


class ReportView(BaseModel):
    report: AnalysisReport
    chart: ChartSpec | None
    range_key: str


def build_report_view(report: AnalysisReport, range_key: str = "Max") -> ReportView:
    if range_key not in {"1Y", "3Y", "5Y", "Max"}:
        raise ValueError("Unsupported report range")
    chart = report.chart
    if chart and range_key != "Max" and chart.product:
        years = int(range_key[0])
        cutoff = max(point.date for point in chart.product) - timedelta(days=365 * years)
        chart = ChartSpec(kind=chart.kind, product=[point for point in chart.product if point.date >= cutoff], benchmark=[point for point in chart.benchmark if point.date >= cutoff])
    return ReportView(report=report, chart=chart, range_key=range_key)

