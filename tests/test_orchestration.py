from datetime import date, timedelta

from fund_analyzer.models import AIAnalysis, AIConclusion, AnalysisStatus, CashFlowKind, EvidenceKind, PerformancePoint, PrivateMarketCashFlow, ProductIdentity, ProductType, SourceResult
from fund_analyzer.orchestration import AnalysisRequest, FundAnalyzer, Services


class FakeMF:
    def current_history(self, code):
        start = date(2023, 1, 1)
        points = [PerformancePoint(date=start + timedelta(days=i), value=100 + i * 0.05, series_kind="NAV") for i in range(1000)]
        return SourceResult(source_name="AMFI", available=True, performance_points=points)


class FakeAI:
    def analyze(self, packet):
        evidence_id = packet.evidence[0]["id"]
        item = AIConclusion(text="Evidence supports a balanced long-term assessment.", evidence_ids=[evidence_id])
        return AIAnalysis(pros=[item] * 3, cons=[item] * 3, outlook=item, risks=[item], monitoring=[item], confidence="medium")


class FakeNifty:
    def __init__(self, available=True, error=RuntimeError):
        self.available = available
        self.error = error

    def tri_history(self, benchmark_name):
        if not self.available:
            return SourceResult(source_name="NSE", available=False, error_code="no_data", warnings=[f"NSE returned no TRI rows for {benchmark_name}"])
        start = date(2023, 1, 1)
        points = [PerformancePoint(date=start + timedelta(days=i), value=20000 + i * 5, series_kind="TRI") for i in range(1000)]
        return SourceResult(source_name="NSE", available=True, performance_points=points)


class DownNifty:
    def tri_history(self, benchmark_name):
        raise RuntimeError("network")


def test_mutual_fund_complete_report_uses_nav():
    identity = ProductIdentity(product_type=ProductType.MUTUAL_FUND, name="Example", provider="AMC", scheme_code="1", benchmark="Nifty 500 TRI")
    services = Services(amfi=FakeMF(), ai=FakeAI())
    report = FundAnalyzer(services).analyze(AnalysisRequest(identity=identity))
    assert report.status in {AnalysisStatus.COMPLETE, AnalysisStatus.PARTIAL}
    assert report.chart.kind == "growth_of_100k"
    assert report.ai.pros


def test_aif_without_cash_flows_does_not_create_nav_chart():
    identity = ProductIdentity(product_type=ProductType.AIF, name="Example AIF", provider="Manager")
    report = FundAnalyzer(Services()).analyze(AnalysisRequest(identity=identity))
    assert report.chart is None
    assert report.status is AnalysisStatus.INSUFFICIENT


def test_all_required_sources_down_is_source_unavailable():
    class Down:
        def current_history(self, code):
            return SourceResult(source_name="AMFI", available=False, error_code="network")
    identity = ProductIdentity(product_type=ProductType.MUTUAL_FUND, name="Example", provider="AMC", scheme_code="1")
    report = FundAnalyzer(Services(amfi=Down())).analyze(AnalysisRequest(identity=identity))
    assert report.status is AnalysisStatus.SOURCE_UNAVAILABLE


def test_aif_dated_cash_flows_create_calculated_metrics_and_timeline():
    identity = ProductIdentity(product_type=ProductType.AIF, name="Example AIF", provider="Manager")
    flows = [
        PrivateMarketCashFlow(date=date(2023, 1, 1), kind=CashFlowKind.CONTRIBUTION, amount=100),
        PrivateMarketCashFlow(date=date(2024, 1, 1), kind=CashFlowKind.DISTRIBUTION, amount=20),
        PrivateMarketCashFlow(date=date(2026, 1, 1), kind=CashFlowKind.RESIDUAL_VALUE, amount=110),
    ]

    report = FundAnalyzer(Services()).analyze(AnalysisRequest(identity=identity, cash_flows=flows))

    assert {metric.key for metric in report.metrics} == {"xirr", "tvpi", "dpi", "rvpi"}
    assert all(metric.source_ids for metric in report.metrics)
    assert report.chart is not None
    assert report.chart.kind == "cash_flow_timeline"
    assert [point.value for point in report.chart.product] == [-100, 20, 110]
    assert all(item.kind is EvidenceKind.USER_INPUT for item in report.evidence)
    assert report.status is AnalysisStatus.PARTIAL


def test_mutual_fund_benchmark_series_is_compared_and_charted():
    identity = ProductIdentity(product_type=ProductType.MUTUAL_FUND, name="Example", provider="AMC", scheme_code="1", benchmark="Nifty 500 TRI")
    report = FundAnalyzer(Services(amfi=FakeMF(), nifty=FakeNifty())).analyze(AnalysisRequest(identity=identity))
    assert report.chart is not None
    assert report.chart.benchmark
    assert all(point.series_kind == "TRI" for point in report.chart.benchmark)
    assert any(item.id == "benchmark-series" for item in report.evidence)
    alpha = next(metric for metric in report.metrics if metric.key == "alpha")
    assert alpha.value is not None
    assert report.status is AnalysisStatus.COMPLETE


def test_benchmark_requested_but_unavailable_is_partial_with_warning():
    identity = ProductIdentity(product_type=ProductType.MUTUAL_FUND, name="Example", provider="AMC", scheme_code="1", benchmark="Nifty 500 TRI")
    report = FundAnalyzer(Services(amfi=FakeMF(), nifty=DownNifty())).analyze(AnalysisRequest(identity=identity))
    assert report.chart is not None
    assert not report.chart.benchmark
    assert report.status is AnalysisStatus.PARTIAL
    assert any("Benchmark" in warning for warning in report.warnings)
    assert any(metric.key == "alpha" and metric.value is None for metric in report.metrics)


def test_mutual_fund_without_benchmark_name_is_partial():
    identity = ProductIdentity(product_type=ProductType.MUTUAL_FUND, name="Example", provider="AMC", scheme_code="1")
    report = FundAnalyzer(Services(amfi=FakeMF(), nifty=FakeNifty())).analyze(AnalysisRequest(identity=identity))
    assert report.status is AnalysisStatus.PARTIAL
    assert any("Benchmark" in warning for warning in report.warnings)
