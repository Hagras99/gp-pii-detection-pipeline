"""Tier 1: regex candidates + validators. Fast, deterministic, no models."""
from __future__ import annotations

import re
from typing import Optional

from ..schemas import DetectionSource, EntityType
from .normalize import Normalized, normalize
from .spans import Span, resolve_overlaps
from .validators import card_ok, card_strong, iban_ok, nid_ok

NID_RX = re.compile(r"(?<!\d)[23]\d{13}(?!\d)")
CARD_RX = re.compile(r"(?<!\d)\d(?:[ -]?\d){12,18}(?!\d)")
IBAN_RX = re.compile(r"(?<![A-Za-z0-9])[A-Za-z]{2}\d{2}(?: ?[A-Za-z0-9]){11,30}")
PHONE_RX = re.compile(r"(?<!\d)(?:\+?20[ -]?|0)1[0125](?:[ -]?\d){8}(?!\d)")
EMAIL_RX = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9-]+(?:\.[A-Za-z0-9-]+)*\.[A-Za-z]{2,}")
DIGITS_RX = re.compile(r"(?<!\d)\d{8,17}(?!\d)")
ACCOUNT_KEYWORDS = ("account", "acct", "a/c", "حساب", "الحساب", "رقم")  # "رقم" = "number": weak context
CARD_KEYWORDS = ("card", "visa", "mastercard", "بطاقة", "البطاقة", "فيزا", "ماستر")
ACCOUNT_WINDOW = 25


class Tier1Rules:
    def __init__(self, custom_patterns: Optional[dict[EntityType, str]] = None):
        """custom_patterns: organization formats, e.g. {EntityType.EMPLOYEE_ID: r"\\bNHB-\\d{6}\\b"}."""
        self.custom = {t: re.compile(p) for t, p in (custom_patterns or {}).items()}

    # each finder returns (start, end, type, score) in NORMALIZED coordinates
    def _find(self, n: Normalized):
        t = n.text
        for m in NID_RX.finditer(t):
            if nid_ok(m.group()):
                yield m.start(), m.end(), EntityType.EG_NATIONAL_ID, 0.99
        for m in CARD_RX.finditer(t):
            digits = re.sub(r"\D", "", m.group())
            if not card_ok(digits):
                continue
            # Luhn alone passes ~1 in 10 random numbers, so confidence comes from issuer prefix + context.
            before = t[max(0, m.start() - ACCOUNT_WINDOW):m.start()].lower()
            if card_strong(digits):
                score = 0.95
            elif any(k in before for k in CARD_KEYWORDS):
                score = 0.90
            else:
                score = 0.60
            yield m.start(), m.end(), EntityType.CREDIT_CARD, score
        for m in IBAN_RX.finditer(t):
            yield from self._iban(m)
        for m in PHONE_RX.finditer(t):
            yield m.start(), m.end(), EntityType.PHONE_NUMBER, 0.95
        for m in EMAIL_RX.finditer(t):
            yield m.start(), m.end(), EntityType.EMAIL_ADDRESS, 0.99
        for m in DIGITS_RX.finditer(t):
            before = t[max(0, m.start() - ACCOUNT_WINDOW):m.start()].lower()
            if any(k in before for k in ACCOUNT_KEYWORDS):
                yield m.start(), m.end(), EntityType.ACCOUNT_NUMBER, 0.75
        for etype, rx in self.custom.items():
            for m in rx.finditer(t):
                yield m.start(), m.end(), etype, 0.97

    @staticmethod
    def _iban(m: re.Match):
        """The regex may run past the IBAN into following capitals; shrink until the checksum passes."""
        cand = m.group()
        positions = [i for i, c in enumerate(cand) if c != " "]  # index of each compact char
        for length in range(min(len(positions), 34), 14, -1):
            compact = "".join(cand[i] for i in positions[:length])
            if iban_ok(compact):
                yield m.start(), m.start() + positions[length - 1] + 1, EntityType.IBAN_CODE, 0.99
                return

    def detect(self, original: str) -> list[Span]:
        n = normalize(original)
        spans = []
        for s, e, etype, score in self._find(n):
            o_start, o_end = n.span_to_original(s, e)
            spans.append(Span(o_start, o_end, etype, DetectionSource.rules, score))
        return resolve_overlaps(spans)
