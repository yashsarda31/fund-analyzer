from __future__ import annotations

import ipaddress
import socket
import time
from urllib.parse import urljoin, urlparse

import httpx


class UnsafeUrlError(ValueError):
    pass


class SourceFetchError(RuntimeError):
    pass


def validate_public_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise UnsafeUrlError("Only public http or https URLs are allowed")
    if parsed.username or parsed.password:
        raise UnsafeUrlError("Credentials in URLs are not allowed")
    try:
        addresses = socket.getaddrinfo(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UnsafeUrlError("URL host could not be resolved") from exc
    for address in addresses:
        ip = ipaddress.ip_address(address[4][0])
        if not ip.is_global:
            raise UnsafeUrlError("Private, local, or reserved URL targets are not allowed")
    return url


class SafeHttpClient:
    def __init__(self, transport: httpx.BaseTransport | None = None):
        self.client = httpx.Client(transport=transport, timeout=15, follow_redirects=False, headers={"User-Agent": "IndianFundAnalyzer/0.1 research-tool"})

    def get(self, url: str, *, accepted_types: set[str] | None = None, max_bytes: int = 10_000_000) -> httpx.Response:
        current = validate_public_url(url)
        accepted_types = accepted_types or {"text/plain", "text/html", "application/pdf", "text/csv", "application/json"}
        for redirect_count in range(4):
            response = None
            for attempt in range(3):
                response = self.client.get(current)
                if response.status_code not in {429, 502, 503, 504} or attempt == 2:
                    break
                time.sleep(0.15 * (attempt + 1))
            assert response is not None
            if response.is_redirect:
                if redirect_count == 3:
                    raise SourceFetchError("Too many redirects")
                current = validate_public_url(urljoin(current, response.headers["location"]))
                continue
            response.raise_for_status()
            content_type = response.headers.get("content-type", "").split(";", 1)[0].lower()
            if content_type and content_type not in accepted_types:
                raise SourceFetchError(f"Unsupported content type: {content_type}")
            if len(response.content) > max_bytes:
                raise SourceFetchError("Response exceeds size limit")
            return response
        raise SourceFetchError("Unable to fetch source")

