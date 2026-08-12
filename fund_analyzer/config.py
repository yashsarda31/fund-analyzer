from __future__ import annotations

from dataclasses import dataclass
from typing import Mapping, Any
from urllib.parse import urlparse


@dataclass(frozen=True, repr=False)
class AppConfig:
    base_url: str
    api_key: str
    model: str

    @classmethod
    def load(cls, mapping: Mapping[str, Any]) -> "AppConfig":
        ai = mapping.get("ai", {})
        base_url = str(ai.get("base_url", "")).strip().rstrip("/")
        api_key = str(ai.get("api_key", "")).strip()
        model = str(ai.get("model", "")).strip()
        parsed = urlparse(base_url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("AI base_url must be an http or https endpoint")
        if not api_key or not model:
            raise ValueError("AI api_key and model are required")
        return cls(base_url=base_url, api_key=api_key, model=model)

    def __repr__(self) -> str:
        return f"AppConfig(base_url={self.base_url!r}, api_key='***', model={self.model!r})"

    def redact(self, text: str) -> str:
        return text.replace(self.api_key, "***") if self.api_key else text
