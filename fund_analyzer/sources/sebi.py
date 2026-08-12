from __future__ import annotations

from datetime import datetime
from io import StringIO
import re

import pandas as pd

from ..models import ProductIdentity, ProductType


def parse_sebi_registry(html: str, product_type: ProductType, retrieved_at: datetime) -> list[ProductIdentity]:
    products: list[ProductIdentity] = []
    for table in pd.read_html(StringIO(html)):
        for _, row in table.iterrows():
            mapping = {str(key).strip().lower(): str(value).strip() for key, value in row.items()}
            reg = next((value for key, value in mapping.items() if "registration" in key and re.search(r"IN/(?:AIF|P)\w*", value, re.I)), None)
            name = next((value for key, value in mapping.items() if key == "name" or "trade name" in key), None)
            if reg and name:
                products.append(ProductIdentity(product_type=product_type, name=name, provider=name, registration_id=reg))
    return products

