from __future__ import annotations

import json
import re

import httpx
from pydantic import ValidationError

from ..config import AppConfig
from ..models import AIAnalysis
from .validation import AIValidationError, EvidencePacket, validate_ai_analysis


class AIClient:
    def __init__(self, config: AppConfig, transport: httpx.BaseTransport | None = None):
        self.config = config
        self.http = httpx.Client(transport=transport, timeout=90)

    def _request(self, packet: EvidencePacket, repair: str | None = None) -> AIAnalysis:
        schema = AIAnalysis.model_json_schema()
        prompt = (
            "Analyze this Indian investment product for a private investor with a 3-5 year horizon. "
            "Return JSON matching the supplied schema. Give 3-5 balanced pros and 3-5 cons. "
            "Cite evidence_ids for every conclusion. Distinguish evidence from judgment.\n\n"
            + packet.model_dump_json(indent=2)
        )
        if repair:
            prompt += f"\n\nRepair the previous response because: {repair}"
        payload = {"model": self.config.model, "temperature": 0.2, "messages": [{"role": "system", "content": packet.system_rules}, {"role": "user", "content": prompt}], "response_format": {"type": "json_schema", "json_schema": {"name": "fund_analysis", "schema": schema}}}
        try:
            response = self.http.post(f"{self.config.base_url}/chat/completions", headers={"Authorization": f"Bearer {self.config.api_key}"}, json=payload)
            if response.status_code == 400 and "response_format" in response.text:
                payload.pop("response_format")
                response = self.http.post(f"{self.config.base_url}/chat/completions", headers={"Authorization": f"Bearer {self.config.api_key}"}, json=payload)
            response.raise_for_status()
            content = response.json()["choices"][0]["message"]["content"].strip()
            content = re.sub(r"^```(?:json)?\s*|\s*```$", "", content, flags=re.I)
            return AIAnalysis.model_validate(json.loads(content))
        except (httpx.HTTPError, KeyError, ValueError, ValidationError) as exc:
            raise AIValidationError(self.config.redact(str(exc))) from exc

    def analyze(self, packet: EvidencePacket) -> AIAnalysis:
        try:
            return validate_ai_analysis(self._request(packet), packet)
        except AIValidationError as first:
            try:
                return validate_ai_analysis(self._request(packet, str(first)), packet)
            except AIValidationError as second:
                return AIAnalysis(available=False, limitations=[f"AI analysis unavailable: {self.config.redact(str(second))}"])

