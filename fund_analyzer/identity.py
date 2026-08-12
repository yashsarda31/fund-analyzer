from __future__ import annotations

import re
from typing import Sequence

from pydantic import BaseModel
from rapidfuzz.fuzz import token_set_ratio

from .models import ProductIdentity


LEGAL_SUFFIXES = {"limited", "ltd", "private", "pvt", "llp", "trust"}


def normalize_name(text: str) -> str:
    words = re.sub(r"[^a-z0-9]+", " ", text.lower()).split()
    return " ".join(word for word in words if word not in LEGAL_SUFFIXES)


class IdentityMatch(BaseModel):
    identity: ProductIdentity
    score: float


class IdentityResolution(BaseModel):
    matches: list[IdentityMatch]
    requires_confirmation: bool = True
    ambiguous: bool = False


def rank_matches(query: str, candidates: Sequence[ProductIdentity]) -> list[IdentityMatch]:
    normalized = normalize_name(query)
    ranked = [
        IdentityMatch(identity=item, score=float(token_set_ratio(normalized, normalize_name(f"{item.provider} {item.name}"))))
        for item in candidates
    ]
    return sorted(ranked, key=lambda match: match.score, reverse=True)


def resolve_identity(query: str, candidates: Sequence[ProductIdentity]) -> IdentityResolution:
    matches = rank_matches(query, candidates)
    ambiguous = not matches or matches[0].score < 90
    if len(matches) > 1 and matches[0].score - matches[1].score <= 10:
        ambiguous = True
    return IdentityResolution(matches=matches, requires_confirmation=True, ambiguous=ambiguous)


def identity_consistent(expected: ProductIdentity, found_text: str) -> bool:
    haystack = normalize_name(found_text)
    return token_set_ratio(normalize_name(expected.name), haystack) >= 75 and token_set_ratio(normalize_name(expected.provider), haystack) >= 60

