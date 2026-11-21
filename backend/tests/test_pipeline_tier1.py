import json, random, sys, pathlib
import pytest

from app.evaluation.metrics import score_exact
from app.pipeline.normalize import normalize
from app.pipeline.spans import Span, resolve_overlaps
from app.pipeline.tier1_rules import Tier1Rules
from app.pipeline.validators import card_ok, card_strong, iban_ok, luhn_ok, nid_ok
from app.schemas import DetectionSource, EntityType as T

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1] / "tools"))
import gen_eg_finance_pii as gen  # noqa: E402

RULES = Tier1Rules({T.EMPLOYEE_ID: r"(?<![A-Za-z0-9])NHB-\d{6}(?!\d)", T.CLIENT_ID: r"(?<![A-Za-z0-9])CL-\d{7}(?!\d)"})
ID_OK = "29001010123446"       # structure valid: century 2, 1990-01-01, governorate 01
ID_AR = "٢٩٠٠١٠١٠١٢٣٤٤٦"


def found(text, rules=RULES):
    return [(text[s.start:s.end], s.type) for s in rules.detect(text)]


# ------------------------------------------------------------------ normalization
def test_normalize_digits_are_length_preserving():
    n = normalize("ID ٢٩٠ ۰۱۲ 123")
    assert n.text == "ID 290 012 123" and len(n.text) == len("ID ٢٩٠ ۰۱۲ 123")


def test_normalize_removes_invisible_chars_and_maps_offsets_back():
    original = "x \u200f٢٩٠٠١٠١\u200b٠١٢٣٤٤٦ y"
    n = normalize(original)
    assert n.text == "x 29001010123446 y"
    s = n.text.index("2")
    start, end = n.span_to_original(s, s + 14)
    assert original[start:end] == "٢٩٠٠١٠١\u200b٠١٢٣٤٤٦"   # the span covers the hidden char in the middle


# ------------------------------------------------------------------ validators
def test_validators_positive_and_negative():
    assert luhn_ok("4111111111111111") and not luhn_ok("4111111111111112")
    assert card_strong("4111111111111111") and not card_strong("1234567812345670")  # Luhn ok, no issuer prefix
    assert iban_ok("GB82 WEST 1234 5698 7654 32") and not iban_ok("GB82 WEST 1234 5698 7654 33")
    assert nid_ok(ID_OK)
    assert not nid_ok("29013010123446")   # month 13
    assert not nid_ok("49001010123446")   # century digit 4
    assert not nid_ok("29001019923446")   # unknown governorate 99
    assert not nid_ok("29002300123446")   # 30 February


# ------------------------------------------------------------------ Tier 1 detection
def test_national_id_in_arabic_digits_returns_original_offsets():
    text = f"الرقم القومي {ID_AR}."
    assert found(text) == [(ID_AR, T.EG_NATIONAL_ID)]


def test_national_id_with_hidden_rtl_mark_is_still_found():
    hidden = ID_AR[:7] + "\u200f" + ID_AR[7:]
    text = f"ID: {hidden} ok"
    assert found(text) == [(hidden, T.EG_NATIONAL_ID)]


def test_phone_formats():
    for ph in ("01012345678", "+201012345678", "+20 101 234 5678", "٠١٠١٢٣٤٥٦٧٨"):
        assert (ph, T.PHONE_NUMBER) in found(f"call {ph} now"), ph


def test_card_with_separators_and_iban_and_email():
    text = "card 4111 1111 1111 1111, mail ahmed.ali@mail.example, iban GB82 WEST 1234 5698 7654 32 FAILED"
    got = dict(found(text))
    assert got["4111 1111 1111 1111"] == T.CREDIT_CARD
    assert got["ahmed.ali@mail.example"] == T.EMAIL_ADDRESS
    assert got["GB82 WEST 1234 5698 7654 32"] == T.IBAN_CODE      # the trailing word FAILED is trimmed off


def test_custom_org_patterns():
    assert found("employee NHB-004821 and client CL-1234567") == [("NHB-004821", T.EMPLOYEE_ID), ("CL-1234567", T.CLIENT_ID)]


# ------------------------------------------------------------------ negatives (what must NOT be flagged)
@pytest.mark.parametrize("text", [
    "order 29013010123446 shipped",         # 14 digits, impossible date -> not an ID
    "ref 1234567812345670",                  # Luhn-valid 16 digits but no issuer prefix, no card context -> weak
    "total 12,500 EGP due 2025",             # amounts and years are not Tier 1 entities
    "version 3.14.159 build 2024",
])
def test_negatives_do_not_produce_strong_findings(text):
    strong = [(t, ty) for (t, ty) in found(text) if ty in (T.EG_NATIONAL_ID, T.PHONE_NUMBER, T.EMAIL_ADDRESS, T.IBAN_CODE)]
    assert strong == []


def test_unprefixed_luhn_number_is_only_weakly_scored_as_card():
    spans = RULES.detect("ref 1234567812345670")
    assert spans and spans[0].type == T.CREDIT_CARD and spans[0].score < 0.7


def test_account_context_beats_weak_card_match():
    # Luhn-valid but no issuer prefix: the weak card match (0.60) must lose to the account-context match (0.75)
    text = "account number 1000000000009"
    assert found(text) == [("1000000000009", T.ACCOUNT_NUMBER)]


def test_card_context_promotes_weak_match():
    text = "my card 1000000000009 was blocked"
    assert found(text) == [("1000000000009", T.CREDIT_CARD)]


# ------------------------------------------------------------------ merge policy
def test_merge_prefers_higher_score_then_length():
    a = Span(0, 10, T.PHONE_NUMBER, DetectionSource.rules, 0.95)
    b = Span(2, 8, T.IBAN_CODE, DetectionSource.rules, 0.99)
    c = Span(20, 25, T.PERSON, DetectionSource.ner, 0.8)
    assert resolve_overlaps([a, b, c]) == [b, c]


def test_iban_wins_over_phone_lookalike_inside_it():
    text = "IBAN EG380019000500000000263180002 here"   # contains digit runs that look phone-like
    types = [ty for _, ty in found(text)]
    assert T.IBAN_CODE in types and T.PHONE_NUMBER not in types


# ------------------------------------------------------------------ regression gate on synthetic data
def test_synthetic_corpus_regression_gate():
    """Circular by construction: my generator and my detectors share assumptions. It guards against
    regressions and checks Arabic-digit / spacing variants; it does NOT measure real-world accuracy."""
    rng = random.Random(123)
    gold, pred = {}, {}
    for i in range(1500):
        lang, tpl, needed = rng.choice(gen.TEMPLATES)
        text, spans = gen.render(lang, tpl, set(needed), rng)
        gold[i] = [(s["start"], s["end"], s["label"]) for s in spans]
        pred[i] = [(s.start, s.end, s.type.value) for s in RULES.detect(text)]
    target = {"EG_NATIONAL_ID", "CREDIT_CARD", "IBAN_CODE", "PHONE_NUMBER", "EMAIL_ADDRESS", "ACCOUNT_NUMBER",
              "EMPLOYEE_ID", "CLIENT_ID"}
    res = score_exact(gold, pred, target)
    assert res["MICRO"]["f1"] >= 0.99
    for t in ("EG_NATIONAL_ID", "IBAN_CODE", "PHONE_NUMBER", "EMAIL_ADDRESS"):
        assert res[t]["f1"] == 1.0, (t, res[t])
