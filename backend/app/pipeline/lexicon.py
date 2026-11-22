"""Detect organization-specific project names in the original prompt."""
import re
from collections.abc import Iterable

from ..schemas import DetectionSource, EntityType
from .spans import Span


class OrganizationLexicon:
    def __init__(self, terms: Iterable[str]):
        entries = {term.strip() for term in terms if term.strip()}
        self.patterns = [
            re.compile(rf"(?<!\w){re.escape(term)}(?!\w)", re.IGNORECASE)
            for term in sorted(entries)
        ]

    def detect(self, prompt: str) -> list[Span]:
        return [
            Span(match.start(), match.end(), EntityType.PROJECT_CODENAME, DetectionSource.lexicon, 0.90)
            for pattern in self.patterns
            for match in pattern.finditer(prompt)
        ]
