from __future__ import annotations

from datetime import datetime
from io import StringIO
import re

import pandas as pd

from ..models import EvidenceItem, EvidenceKind, SourceRef


def parse_rbi_tbill(html: str, retrieved_at: datetime) -> EvidenceItem:
    for table in pd.read_html(StringIO(html)):
        for _, row in table.iterrows():
            values = [str(value).strip() for value in row.tolist()]
            if len(values) < 2:
                continue
            try:
                observed = pd.to_datetime(values[0], dayfirst=True).date()
                yield_value = float(re.sub(r"[^0-9.\-]", "", values[1])) / 100
            except (ValueError, TypeError):
                continue
            return EvidenceItem(id="rbi-91d-tbill", kind=EvidenceKind.VERIFIED_FACT, label="91-day T-bill cut-off yield", value=yield_value, unit="annual rate", source=SourceRef(title="91-day Treasury Bill auction", publisher="Reserve Bank of India", url="https://www.rbi.org.in/", observed_at=observed, retrieved_at=retrieved_at))
    raise ValueError("No 91-day T-bill observation found")

