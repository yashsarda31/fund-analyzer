import fitz

from fund_analyzer.models import ProductIdentity, ProductType
from fund_analyzer.pdf_extract import extract_pdf


def make_pdf(text: str) -> bytes:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_textbox(fitz.Rect(40, 40, 560, 800), text, fontsize=10)
    result = doc.tobytes()
    doc.close()
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

