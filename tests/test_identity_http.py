import pytest
import httpx
import socket

from fund_analyzer.identity import resolve_identity
from fund_analyzer.models import ProductIdentity, ProductType
from fund_analyzer.sources.http import SafeHttpClient, SourceFetchError, UnsafeUrlError, validate_public_url


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


def test_http_client_enforces_type_size_and_redirect(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))])
    good = SafeHttpClient(httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-type": "text/plain"}, content=b"ok")))
    assert good.get("https://example.com", accepted_types={"text/plain"}).text == "ok"
    bad_type = SafeHttpClient(httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-type": "image/png"}, content=b"x")))
    with pytest.raises(SourceFetchError, match="content type"):
        bad_type.get("https://example.com", accepted_types={"text/plain"})
    too_big = SafeHttpClient(httpx.MockTransport(lambda request: httpx.Response(200, headers={"content-type": "text/plain"}, content=b"12345")))
    with pytest.raises(SourceFetchError, match="size limit"):
        too_big.get("https://example.com", accepted_types={"text/plain"}, max_bytes=4)


def test_http_client_retries_transient_status(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))])
    calls = []
    def handler(request):
        calls.append(request)
        return httpx.Response(503 if len(calls) < 3 else 200, headers={"content-type": "text/plain"}, content=b"ok")
    assert SafeHttpClient(httpx.MockTransport(handler)).get("https://example.com", accepted_types={"text/plain"}).text == "ok"
    assert len(calls) == 3


def test_url_credentials_and_dns_failure_are_rejected(monkeypatch):
    with pytest.raises(UnsafeUrlError, match="Credentials"):
        validate_public_url("https://user:pass@example.com")
    def fail_dns(*args, **kwargs):
        raise socket.gaierror("dns")
    monkeypatch.setattr("socket.getaddrinfo", fail_dns)
    with pytest.raises(UnsafeUrlError, match="resolved"):
        validate_public_url("https://missing.example")


def test_redirect_limit_and_final_http_error(monkeypatch):
    monkeypatch.setattr("socket.getaddrinfo", lambda *args, **kwargs: [(2, 1, 6, "", ("93.184.216.34", 443))])
    redirecting = SafeHttpClient(httpx.MockTransport(lambda request: httpx.Response(302, headers={"location": "https://example.com/again"})))
    with pytest.raises(SourceFetchError, match="redirect"):
        redirecting.get("https://example.com")
    failing = SafeHttpClient(httpx.MockTransport(lambda request: httpx.Response(500, text="down")))
    with pytest.raises(httpx.HTTPStatusError):
        failing.get("https://example.com")
