import fitz

from fund_analyzer.models import EvidenceKind, ProductIdentity, ProductType
from fund_analyzer.pdf_extract import extract_pdf


def make_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(40, 40, 560, 800), text, fontsize=10)
    result = doc.tobytes()
    doc.close()
    return result


def make_scanned_pdf(text: str) -> bytes:
    source = fitz.open(stream=make_pdf(text), filetype="pdf")
    pixmap = source[0].get_pixmap(matrix=fitz.Matrix(2, 2), alpha=False)
    source.close()
    scanned = fitz.open()
    page = scanned.new_page(width=pixmap.width, height=pixmap.height)
    page.insert_image(page.rect, stream=pixmap.tobytes("png"))
    result = scanned.tobytes()
    scanned.close()
    return result


def identity():
    return ProductIdentity(product_type=ProductType.AIF, name="Example Growth Fund II", provider="Example Capital", registration_id="IN/AIF2/22-23/1234")


def test_pdf_extracts_page_linked_facts():
    data = make_pdf("Example Capital\nExample Growth Fund II\nRegistration: IN/AIF2/22-23/1234\nManagement Fee: 2.0% p.a.\nMinimum Investment: INR 1 crore\nLock-in: 3 years\nBenchmark: Nifty 500 TRI\nAs of: 31 July 2026")
    result = extract_pdf(data, identity())
    fee = next(item for item in result.evidence if item.label == "Management fee")
    assert fee.value == 2.0
    assert fee.source.page == 1
    assert result.identity_match == "match"


def test_mismatched_pdf_blocks_document_facts():
    data = make_pdf("Other Manager\nDifferent Opportunity Fund\nManagement Fee: 1.5% p.a.\nAs of: 31 July 2026")
    result = extract_pdf(data, identity())
    assert result.identity_match == "mismatch"
    assert result.evidence == []


def test_scanned_pdf_uses_local_ocr_and_preserves_page_provenance():
    scanned = make_scanned_pdf("image only")
    ocr_text = "Example Capital\nExample Growth Fund II\nTVPI: 1.42x\nAs of: 31 July 2026"

    result = extract_pdf(scanned, identity(), ocr_page=lambda page: ocr_text)

    tvpi = next(item for item in result.evidence if item.label == "TVPI")
    assert tvpi.value == 1.42
    assert tvpi.source.page == 1
    assert tvpi.kind is EvidenceKind.DOCUMENT_EXTRACT
    assert tvpi.confidence < 1
    assert result.ocr_used is True
    assert result.ocr_pages == [1]
    assert any("OCR-derived" in warning for warning in result.warnings)


def test_scanned_pdf_reports_local_ocr_dependency_failure():
    def unavailable(page):
        raise RuntimeError("No tessdata specified and Tesseract is not installed")

    result = extract_pdf(make_scanned_pdf("image only"), identity(), ocr_page=unavailable)

    assert result.identity_match == "unknown"
    assert result.evidence == []
    assert any("local OCR is unavailable" in warning for warning in result.warnings)


def test_local_ocr_attempts_are_capped_for_large_scanned_documents():
    document = fitz.open()
    for _ in range(51):
        document.new_page()
    data = document.tobytes()
    document.close()
    attempts = 0

    def empty_ocr(page):
        nonlocal attempts
        attempts += 1
        return ""

    result = extract_pdf(data, identity(), ocr_page=empty_ocr)

    assert attempts == 50
    assert any("stopped after 50 pages" in warning for warning in result.warnings)
