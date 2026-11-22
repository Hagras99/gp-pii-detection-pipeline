"""Span data model and the overlap-resolution (merge) policy."""
from __future__ import annotations

from dataclasses import dataclass

from ..schemas import DetectionSource, EntityType

# Tie-break order when score and length are equal: more specific / more sensitive first.
TYPE_PRIORITY = [EntityType.SECRET, EntityType.EG_NATIONAL_ID, EntityType.CREDIT_CARD, EntityType.IBAN_CODE,
                 EntityType.EMAIL_ADDRESS, EntityType.PHONE_NUMBER, EntityType.EMPLOYEE_ID, EntityType.CLIENT_ID,
                 EntityType.ACCOUNT_NUMBER, EntityType.PERSON, EntityType.ORGANIZATION, EntityType.LOCATION,
                 EntityType.PROJECT_CODENAME, EntityType.AMOUNT]
_RANK = {t: i for i, t in enumerate(TYPE_PRIORITY)}


@dataclass(frozen=True)
class Span:
    start: int  # character offsets into the ORIGINAL text, end exclusive
    end: int
    type: EntityType
    source: DetectionSource
    score: float

    def overlaps(self, other: "Span") -> bool:
        return self.start < other.end and other.start < self.end


def resolve_overlaps(spans: list[Span]) -> list[Span]:
    """Protect established spans from Tier 3, then rank by score, length and type."""
    protected = [s for s in spans if s.source in (DetectionSource.rules, DetectionSource.lexicon)]
    presidio_offsets = {(s.start, s.end) for s in spans if s.source == DetectionSource.presidio}
    spans = [
        s for s in spans
        if s.source != DetectionSource.ner
        or ((s.start, s.end) not in presidio_offsets and not any(s.overlaps(p) for p in protected))
    ]
    ranked = sorted(spans, key=lambda s: (-s.score, -(s.end - s.start), _RANK.get(s.type, 99), s.start))
    chosen: list[Span] = []
    for s in ranked:
        if not any(s.overlaps(c) for c in chosen):
            chosen.append(s)
    return sorted(chosen, key=lambda s: s.start)
