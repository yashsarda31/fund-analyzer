import pytest

from fund_analyzer.identity import resolve_identity
from fund_analyzer.models import ProductIdentity, ProductType
from fund_analyzer.sources.http import UnsafeUrlError, validate_public_url


def test_direct_and_regular_plans_are_not_merged():
    candidates = [
        ProductIdentity(product_type=ProductType.MUTUAL_FUND, name="Example Flexi Cap Fund", provider="Example AMC", plan="Direct", option="Growth"),
        ProductIdentity(product_type=ProductType.MUTUAL_FUND, name="Example Flexi Cap Fund", provider="Example AMC", plan="Regular", option="Growth"),
    ]
    result = resolve_identity("Example Flexi Cap", candidates)
    assert result.requires_confirmation is True
    assert {m.identity.plan for m in result.matches[:2]} == {"Direct", "Regular"}


@pytest.mark.parametrize("url", [
    "file:///C:/secret.txt", "http://127.0.0.1/admin", "http://localhost:8000",
    "http://169.254.169.254/latest/meta-data", "ftp://example.com/file",
])
def test_private_or_non_web_urls_are_rejected(url):
    with pytest.raises(UnsafeUrlError):
        validate_public_url(url)


def test_public_https_url_is_allowed(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))])
    assert str(validate_public_url("https://example.com/factsheet")) == "https://example.com/factsheet"

