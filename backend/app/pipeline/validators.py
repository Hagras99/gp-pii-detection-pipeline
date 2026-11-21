"""Identifier validators. A regex finds candidates; these decide whether a candidate is plausible."""
from __future__ import annotations

import datetime
import re

# Governorate codes inside the Egyptian national ID. FROM MEMORY: verify against an official source.
EG_GOV_CODES = {"01", "02", "03", "04", "11", "12", "13", "14", "15", "16", "17", "18", "19", "21", "22", "23",
                "24", "25", "26", "27", "28", "29", "31", "32", "33", "34", "35", "88"}


def luhn_ok(digits: str) -> bool:
    if not digits.isdigit():
        return False
    d = [int(c) for c in digits][::-1]
    return (sum(d[0::2]) + sum(sum(divmod(2 * x, 10)) for x in d[1::2])) % 10 == 0


def card_ok(digits: str) -> bool:
    return 13 <= len(digits) <= 19 and luhn_ok(digits)


def card_strong(digits: str) -> bool:
    """Luhn-valid AND a known issuer prefix with that scheme's usual length (Visa, Mastercard, Amex, Discover,
    Diners, JCB, UnionPay). Egypt's national Meeza scheme is NOT covered: I do not know its prefix."""
    if not card_ok(digits):
        return False
    n, p2, p4 = len(digits), int(digits[:2]), int(digits[:4])
    if digits[0] == "4":
        return n in (13, 16, 19)
    if n == 16 and (51 <= p2 <= 55 or 2221 <= p4 <= 2720):
        return True
    if n == 15 and p2 in (34, 37):
        return True
    if n == 14 and (p2 in (36, 38) or 300 <= int(digits[:3]) <= 305):
        return True
    if 16 <= n <= 19 and (digits.startswith(("6011", "65")) or 644 <= int(digits[:3]) <= 649 or p2 == 62):
        return True
    return n in (16, 17, 18, 19) and p2 == 35


def iban_ok(compact: str) -> bool:
    """ISO 13616 mod-97 check, plus the Egyptian length (29). Other countries: generic length 15-34."""
    s = compact.replace(" ", "").upper()
    if not re.fullmatch(r"[A-Z]{2}\d{2}[A-Z0-9]{11,30}", s):
        return False
    if s.startswith("EG") and len(s) != 29:
        return False
    r = s[4:] + s[:4]
    return int("".join(str(int(c, 36)) for c in r)) % 97 == 1


def nid_ok(digits: str) -> bool:
    """Egyptian national ID STRUCTURE: century digit, real calendar date, known governorate code.
    The 14th (check) digit is NOT validated: no public algorithm is known to me."""
    if not (len(digits) == 14 and digits.isdigit() and digits[0] in "23" and digits[7:9] in EG_GOV_CODES):
        return False
    year = (1900 if digits[0] == "2" else 2000) + int(digits[1:3])
    try:
        datetime.date(year, int(digits[3:5]), int(digits[5:7]))
    except ValueError:
        return False
    return True
