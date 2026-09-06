from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Callable

import pymupdf
from pydantic import BaseModel, Field

from .identity import identity_consistent
from .models import EvidenceItem, EvidenceKind, ProductIdentity, SourceRef


class PdfExtraction(BaseModel):
    identity_match: str
    evidence: list[EvidenceItem] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    text_by_page: list[str] = Field(default_factory=list)
    ocr_used: bool = False
    ocr_pages: list[int] = Field(default_factory=list)


FIELD_PATTERNS = {
    "Management fee": (r"management\s+fee\s*[:\-]\s*(\d+(?:\.\d+)?)\s*%", "% p.a."),
    "Performance fee": (r"performance\s+fee\s*[:\-]\s*(\d+(?:\.\d+)?)\s*%", "%"),
    "Lock-in": (r"lock[ -]?in\s*[:\-]\s*([^\n]+)", None),
    "Minimum investment": (r"minimum\s+investment\s*[:\-]\s*([^\n]+)", None),
    "Benchmark": (r"benchmark\s*[:\-]\s*([^\n]+)", None),
    "AUM": (r"(?:aum|corpus)\s*[:\-]\s*([^\n]+)", None),
    "IRR": (r"(?:net\s+)?irr\s*[:\-]\s*(\d+(?:\.\d+)?)\s*%", "%"),
    "TVPI": (r"tvpi\s*[:\-]\s*(\d+(?:\.\d+)?)\s*x?", "x"),
    "DPI": (r"dpi\s*[:\-]\s*(\d+(?:\.\d+)?)\s*x?", "x"),
    "RVPI": (r"rvpi\s*[:\-]\s*(\d+(?:\.\d+)?)\s*x?", "x"),
    "MOIC": (r"moic\s*[:\-]\s*(\d+(?:\.\d+)?)\s*x?", "x"),
    "1-year return": (r"1[ -]?year\s+return\s*[:\-]\s*(\-?\d+(?:\.\d+)?)\s*%", "%"),
    "3-year return": (r"3[ -]?year\s+return\s*[:\-]\s*(\-?\d+(?:\.\d+)?)\s*%", "%"),
    "5-year return": (r"5[ -]?year\s+return\s*[:\-]\s*(\-?\d+(?:\.\d+)?)\s*%", "%"),
}

MAX_OCR_PAGES = 50
OcrPage = Callable[[pymupdf.Page], str]


def _find_tessdata() -> str:
    candidates = [
        Path(__file__).resolve().parents[1] / ".tools" / "Tesseract-OCR" / "tessdata",
        Path(r"C:\Program Files\Tesseract-OCR\tessdata"),
        Path.home() / "AppData" / "Local" / "Programs" / "Tesseract-OCR" / "tessdata",
        # Linux (Debian/Ubuntu) system packages, e.g. Streamlit Community Cloud with packages.txt
        Path("/usr/share/tesseract-ocr/5/tessdata"),
        Path("/usr/share/tesseract-ocr/4.00/tessdata"),
        Path("/usr/share/tessdata"),
    ]
    for candidate in candidates:
        if (candidate / "eng.traineddata").is_file():
            return str(candidate)
    return pymupdf.get_tessdata()


def _local_ocr_page(page: pymupdf.Page) -> str:
    text_page = page.get_textpage_ocr(language="eng", dpi=200, full=True, tessdata=_find_tessdata())
    return page.get_text("text", textpage=text_page, sort=True)


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


def extract_pdf(data: bytes, expected_identity: ProductIdentity, *, ocr_page: OcrPage | None = None) -> PdfExtraction:
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
        pages: list[str] = []
        ocr_pages: list[int] = []
        ocr_attempts = 0
        warnings: list[str] = []
        ocr = ocr_page or _local_ocr_page
        for page_number, page in enumerate(doc, 1):
            text = page.get_text("text", sort=True)
            if len(re.sub(r"\s+", "", text)) < 40:
                if ocr_attempts >= MAX_OCR_PAGES:
                    warnings.append(f"Local OCR stopped after {MAX_OCR_PAGES} pages")
                else:
                    ocr_attempts += 1
                    try:
                        recognized = ocr(page)
                    except Exception:
                        warnings.append("Scanned page detected, but local OCR is unavailable. Install Tesseract OCR with English language data.")
                    else:
                        if len(re.sub(r"\s+", "", recognized)) >= 10:
                            text = recognized
                            ocr_pages.append(page_number)
            pages.append(text)
    finally:
        doc.close()
    full_text = "\n".join(pages)
    if len(re.sub(r"\s+", "", full_text)) < 40:
        if not warnings:
            warnings.append("Image-only or empty PDF; local OCR produced insufficient text")
        return PdfExtraction(identity_match="unknown", warnings=list(dict.fromkeys(warnings)), text_by_page=pages, ocr_used=bool(ocr_pages), ocr_pages=ocr_pages)
    if ocr_pages:
        warnings.append("OCR-derived fields are lower-confidence document extracts; verify them against the scanned factsheet before relying on calculations.")
    if not identity_consistent(expected_identity, full_text):
        warnings.append("PDF identity does not match the confirmed product")
        return PdfExtraction(identity_match="mismatch", warnings=list(dict.fromkeys(warnings)), text_by_page=pages, ocr_used=bool(ocr_pages), ocr_pages=ocr_pages)
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
                kind=EvidenceKind.DOCUMENT_EXTRACT if page_number in ocr_pages else EvidenceKind.VERIFIED_FACT,
                label=label,
                value=value,
                unit=unit,
                source=SourceRef(title="Uploaded factsheet", publisher=expected_identity.provider, observed_at=observed, retrieved_at=retrieved, page=page_number),
                excerpt=excerpt,
                confidence=0.7 if page_number in ocr_pages else 1.0,
            ))
    return PdfExtraction(identity_match="match", evidence=evidence, warnings=list(dict.fromkeys(warnings)), text_by_page=pages, ocr_used=bool(ocr_pages), ocr_pages=ocr_pages)
