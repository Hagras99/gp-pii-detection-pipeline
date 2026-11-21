"""
Normalization for DETECTION ONLY. The original text is never modified.

* Any Unicode decimal digit (Arabic-Indic ٠١٢, Persian ۰۱۲, full-width) -> ASCII 0-9.
* Invisible/formatting characters that people paste into IDs and numbers (zero-width space/joiners,
  left-to-right / right-to-left marks, bidi embeddings, BOM, Arabic tatweel) are REMOVED.

Removal changes the text length, so we keep `to_orig`: for each normalized character, its index in the
original. Spans found on the normalized text are mapped back with `span_to_original`.
"""
from __future__ import annotations

import unicodedata
from dataclasses import dataclass

INVISIBLE = set("\u200b\u200c\u200d\u200e\u200f\u202a\u202b\u202c\u202d\u202e\u2066\u2067\u2068\u2069\ufeff\u0640")


@dataclass(frozen=True)
class Normalized:
    text: str
    to_orig: tuple[int, ...]  # len == len(text)
    orig_len: int

    def span_to_original(self, start: int, end: int) -> tuple[int, int]:
        """Map [start, end) in normalized text to [start, end) in the original text."""
        if not (0 <= start < end <= len(self.text)):
            raise ValueError("span out of range")
        return self.to_orig[start], self.to_orig[end - 1] + 1


def normalize(original: str) -> Normalized:
    chars: list[str] = []
    idx: list[int] = []
    for i, ch in enumerate(original):
        if ch in INVISIBLE:
            continue
        chars.append(str(unicodedata.decimal(ch)) if ch.isdecimal() else ch)
        idx.append(i)
    return Normalized("".join(chars), tuple(idx), len(original))
