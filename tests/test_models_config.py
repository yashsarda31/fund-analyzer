from datetime import date, datetime, timezone

import pytest

from fund_analyzer.config import AppConfig
from fund_analyzer.models import EvidenceItem, EvidenceKind, SourceRef


def test_evidence_requires_observation_and_retrieval_dates():
    source = SourceRef(
        title="AMFI NAV",
        publisher="AMFI",
        url="https://www.amfiindia.com/",
        observed_at=date(2026, 8, 11),
        retrieved_at=datetime(2026, 8, 12, tzinfo=timezone.utc),
    )
    item = EvidenceItem(
        id="amfi-nav-1",
        kind=EvidenceKind.VERIFIED_FACT,
        label="NAV",
        value=123.45,
        unit="INR",
        source=source,
    )
    assert item.source.publisher == "AMFI"


def test_config_redacts_key_and_rejects_non_http_endpoint():
    config = AppConfig.load(
        {"ai": {"base_url": "https://api.example/v1", "api_key": "secret", "model": "minimax-m3"}}
    )
    assert "secret" not in repr(config)
    with pytest.raises(ValueError, match="http"):
        AppConfig.load({"ai": {"base_url": "file:///tmp", "api_key": "x", "model": "m"}})
