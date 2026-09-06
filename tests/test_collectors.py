from datetime import datetime, timezone

from fund_analyzer.models import ProductType
from fund_analyzer.sources.amfi import parse_amfi_directory, parse_amfi_history
from fund_analyzer.sources.apmi import parse_apmi_performance
from fund_analyzer.sources.nifty import parse_nifty_tri
from fund_analyzer.sources.rbi import parse_rbi_tbill
from fund_analyzer.sources.sebi import parse_sebi_registry


NOW = datetime(2026, 8, 12, tzinfo=timezone.utc)


def test_amfi_preserves_plan_and_parses_history():
    text = "Scheme Code;ISIN Div Payout/ISIN Growth;ISIN Div Reinvestment;Scheme Name;Net Asset Value;Date\nOpen Ended Schemes ( Equity Scheme - Flexi Cap Fund )\n1001;INF0001;;Example Flexi Cap Fund - Direct Plan - Growth;123.40;11-Aug-2026\n1002;INF0002;;Example Flexi Cap Fund - Regular Plan - Growth;120.00;11-Aug-2026"
    products = parse_amfi_directory(text, NOW)
    assert {p.plan for p in products} == {"Direct", "Regular"}
    points = parse_amfi_history(text, "1001", NOW)
    assert points[0].value == 123.4


def test_apmi_na_is_missing_not_zero():
    html = """<table><tr><th>PMS Provider Name</th><th>IA Name</th><th>AUM</th><th>1 Year</th><th>5 Years</th></tr><tr><td>Example PMS Pvt Ltd</td><td>Focused Value</td><td>₹125.5</td><td>14.2</td><td>NA</td></tr></table>"""
    result = parse_apmi_performance(html, NOW)
    assert result[0]["returns"]["5y"] is None
    assert result[0]["aum_crore"] == 125.5


def test_regulator_benchmark_and_rate_parsers():
    sebi = """<table><tr><th>Name</th><th>Registration No.</th></tr><tr><td>Example Growth Trust</td><td>IN/AIF2/22-23/1234</td></tr></table>"""
    assert parse_sebi_registry(sebi, ProductType.AIF, NOW)[0].registration_id == "IN/AIF2/22-23/1234"
    nifty = {"data": [{"Date": "11-Aug-2026", "Total Returns Index": "25,100.2"}]}
    assert parse_nifty_tri(nifty, NOW)[0].series_kind == "TRI"
    rbi = "<table><tr><th>Date</th><th>91 day T-Bill</th></tr><tr><td>07-Aug-2026</td><td>5.52</td></tr></table>"
    assert parse_rbi_tbill(rbi, NOW).value == 0.0552


def test_nifty_parser_accepts_json_encoded_string_payload():
    nifty = '{"d": "[{\\"Date\\": \\"11-Aug-2026\\", \\"NIFTY 500 Total Returns Index\\": \\"25,100.2\\"}]"}'
    import json as json_module
    payload = json_module.loads(nifty)
    data = payload.get("d", payload)
    if isinstance(data, str):
        data = json_module.loads(data)
    points = parse_nifty_tri(data, NOW)
    assert points[0].value == 25100.2


def test_resolve_nifty_index_maps_known_and_unknown_names():
    from fund_analyzer.sources.nifty import resolve_nifty_index
    assert resolve_nifty_index("Nifty 500 TRI") == "NIFTY 500"
    assert resolve_nifty_index("Nifty Smallcap 250 TRI") == "NIFTY SMALLCAP 250"
    assert resolve_nifty_index("nifty midcap 150 tri") == "NIFTY MIDCAP 150"
    assert resolve_nifty_index("Custom Benchmark TRI") == "CUSTOM BENCHMARK"
    assert resolve_nifty_index("Nifty 500") == "NIFTY 500"
