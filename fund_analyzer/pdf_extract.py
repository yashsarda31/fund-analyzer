from __future__ import annotations

import re
from datetime import date, datetime, timezone

import pymupdf
from pydantic import BaseModel, Field

from .identity import identity_consistent
from .models import EvidenceItem, EvidenceKind, ProductIdentity, SourceRef


class PdfExtraction(BaseModel):
    identity_match: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    text_by_page: list[str] = Field(default_factory=list)


FIELD_PATTERNS = {
    "Management fee": (r"management\s+fee\s*[:\-]\s*(\d+(?:\.\d+)?)\s*%", "% p.a."),
    "Performance fee": (r"performance\s+fee\s*[:\-]\s*(\d+(?:\.\d+)?)\s*%", "%"),
    "Lock-in": (r"lock[ -]?in\s*[:\-]\s*([^\n]+)", None),
    "Minimum investment": (r"minimum\s+investment\s*[:\-]\s*([^\n]+)", None),
    "Benchmark": (r"benchmark\s*[:\-]\s*([^\n]+)", None),
    "AUM": (r"(?:aum|corpus)\s*[:\-]\s*([^\n]+)", None),
}


def _observed_date(text: str) -> date:
    match = re.search(r"(?:as\s+of|reporting\s+date)\s*[:\-]\s*(\d{1,2}\s+[A-Za-z]+\s+\d{4}|\d{1,2}[-/]\w+[-/]\d{4})", text, re.I)
    if not match:
        return date.today()
    for fmt in ("%d %B %Y", "%d %b %Y", "%d-%b-%Y", "%d/%m/%Y"):
        try:
            return datetime.strptime(match.group(1), fmt).date()
        except ValueError:
            continue
    return date.today()


def extract_pdf(data: bytes, expected_identity: ProductIdentity) -> PdfExtraction:
    if len(data) > 15_000_000:
        return PdfExtraction(identity_match="unknown", warnings=["PDF exceeds the 15 MB limit"])
    try:
        doc = pymupdf.open(stream=data, filetype="pdf")
    except Exception:
        return PdfExtraction(identity_match="unknown", warnings=["PDF is malformed or unsupported"])
    try:
        if doc.needs_pass:
            return PdfExtraction(identity_match="unknown", warnings=["Encrypted PDFs are unsupported"])
        if doc.page_count > 150:
            return PdfExtraction(identity_match="unknown", warnings=["PDF exceeds the 150-page limit"])
        pages = [page.get_text("text") for page in doc]
    finally:
        doc.close()
    full_text = "\n".join(pages)
    if len(re.sub(r"\s+", "", full_text)) < 40:
        return PdfExtraction(identity_match="unknown", warnings=["Image-only or empty PDF; OCR is not supported"], text_by_page=pages)
    if not identity_consistent(expected_identity, full_text):
        return PdfExtraction(identity_match="mismatch", warnings=["PDF identity does not match the confirmed product"], text_by_page=pages)
    observed = _observed_date(full_text)
    retrieved = datetime.now(timezone.utc)
    evidence: list[EvidenceItem] = []
    for page_number, page_text in enumerate(pages, 1):
        for label, (pattern, unit) in FIELD_PATTERNS.items():
            match = re.search(pattern, page_text, re.I)
            if not match:
                continue
            raw = match.group(1).strip()
            value: str | float = float(raw) if unit and re.fullmatch(r"\d+(?:\.\d+)?", raw) else raw
            excerpt = page_text[max(0, match.start() - 40): min(len(page_text), match.end() + 80)].strip()
            evidence.append(EvidenceItem(
                id=f"pdf-p{page_number}-{re.sub(r'[^a-z0-9]+', '-', label.lower()).strip('-')}",
                kind=EvidenceKind.VERIFIED_FACT,
                label=label,
                value=value,
                unit=unit,
                source=SourceRef(title="Uploaded factsheet", publisher=expected_identity.provider, observed_at=observed, retrieved_at=retrieved, page=page_number),
                excerpt=excerpt,
            ))
    return PdfExtraction(identity_match="match", evidence=evidence, text_by_page=pages)

