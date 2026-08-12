from datetime import date, timedelta

from fund_analyzer.models import AIAnalysis, AIConclusion, AnalysisStatus, PerformancePoint, ProductIdentity, ProductType, SourceResult
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
