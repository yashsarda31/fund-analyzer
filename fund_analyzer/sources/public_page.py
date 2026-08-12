from __future__ import annotations

from datetime import date, datetime, timezone

from bs4 import BeautifulSoup
from pydantic import BaseModel, Field

from ..identity import identity_consistent
from ..models import EvidenceItem, EvidenceKind, ProductIdentity, SourceRef
from .http import SafeHttpClient


class PublicPageResult(BaseModel):
    identity_match: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


def extract_public_page(html: str, url: str, identity: ProductIdentity, retrieved_at: datetime | None = None) -> PublicPageResult:
    soup = BeautifulSoup(html, "lxml")
    for node in soup(["script", "style", "form", "noscript"]):
        node.decompose()
    text = soup.get_text("\n", strip=True)
    if not identity_consistent(identity, text):
        return PublicPageResult(identity_match="mismatch", warnings=["Web page identity does not match the selected product"])
    source = SourceRef(title=soup.title.string.strip() if soup.title and soup.title.string else "Public product page", publisher=identity.provider, url=url, observed_at=date.today(), retrieved_at=retrieved_at or datetime.now(timezone.utc))
    return PublicPageResult(identity_match="match", evidence=[EvidenceItem(id="web-product-description", kind=EvidenceKind.VERIFIED_FACT, label="Official product description", value=text[:1500], source=source, excerpt=text[:500], confidence=0.8)])


class PublicPageCollector:
    def __init__(self, http: SafeHttpClient | None = None):
        self.http = http or SafeHttpClient()

    def extract(self, url: str, identity: ProductIdentity) -> PublicPageResult:
        response = self.http.get(url, accepted_types={"text/html", "text/plain"})
        return extract_public_page(response.text, url, identity)
