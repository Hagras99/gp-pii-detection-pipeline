#!/usr/bin/env python3
"""
Synthetic Egyptian finance prompts with PII span labels (Arabic / English / mixed).

Everything here is FAKE: names are random combinations, the bank/company/project
names are invented, email domains use the reserved ".example" TLD.

Run:   python gen_eg_finance_pii.py --n 3000 --seed 7 --out eg_finance_pii.jsonl
Output: one JSON object per line:
  {"id", "lang", "text", "spans": [{"start","end","label","text","key","needed"}]}

`needed` = heuristic flag: does the user's TASK in this template need that entity
(e.g. a name used in a reply's salutation)? It is written by the template author,
not by a human annotator -> review before using it as ground truth.
"""
import argparse, datetime, json, random, re
from collections import Counter

AR_DIGITS = str.maketrans("0123456789", "٠١٢٣٤٥٦٧٨٩")
EN_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")

# (arabic, latin transliteration)
MALE = [("محمد", "Mohamed"), ("أحمد", "Ahmed"), ("محمود", "Mahmoud"), ("مصطفى", "Mostafa"),
        ("عمر", "Omar"), ("كريم", "Karim"), ("يوسف", "Youssef"), ("حسن", "Hassan"),
        ("خالد", "Khaled"), ("طارق", "Tarek"), ("عمرو", "Amr"), ("هشام", "Hesham"),
        ("إبراهيم", "Ibrahim"), ("علي", "Ali")]
FEMALE = [("منى", "Mona"), ("سارة", "Sara"), ("فاطمة", "Fatma"), ("نور", "Nour"),
          ("هدى", "Hoda"), ("ياسمين", "Yasmin"), ("دعاء", "Doaa"), ("مريم", "Mariam"),
          ("رنا", "Rana"), ("آية", "Aya"), ("هبة", "Heba"), ("سلمى", "Salma")]
FAMILY = [("عادل", "Adel"), ("حسين", "Hussein"), ("فهمي", "Fahmy"), ("الشرقاوي", "ElSharkawy"),
          ("منصور", "Mansour"), ("سليمان", "Soliman"), ("عبد الرحمن", "AbdelRahman"),
          ("النجار", "ElNaggar"), ("عثمان", "Osman"), ("الجمل", "ElGamal"), ("زيدان", "Zidan"),
          ("السيد", "ElSayed"), ("عبد الله", "Abdallah")]
CITIES = [("القاهرة", "Cairo"), ("الجيزة", "Giza"), ("الإسكندرية", "Alexandria"),
          ("المنصورة", "Mansoura"), ("أسيوط", "Assiut"), ("طنطا", "Tanta")]
ORGS = [("شركة النيل للمقاولات", "Nile Contracting Co."), ("مجموعة دلتا للصناعات", "Delta Industries Group"),
        ("شركة الهرم للتجارة", "Haram Trading"), ("مصنع الفيروز للأغذية", "Firouz Foods Factory")]
PROJECTS = [("مشروع الصقر", "Project Falcon"), ("مشروع اللوتس", "Project Lotus"),
            ("مشروع أبو الهول", "Project Sphinx"), ("مشروع نفرتيتي", "Project Nefertiti")]
BANK_NAME_PREFIX = "NHB"  # fictional "Nile Horizon Bank" employee-id prefix

# Governorate codes used inside the national ID (from memory -- VERIFY against an official source)
GOV_CODES = ["01", "02", "03", "04", "11", "12", "13", "14", "15", "16", "17", "18", "19",
             "21", "22", "23", "24", "25", "26", "27", "28", "29", "31", "32", "33", "34", "35"]

LABEL = {"PERSON": "PERSON", "NID": "EG_NATIONAL_ID", "PHONE": "PHONE_NUMBER",
         "EMAIL": "EMAIL_ADDRESS", "IBAN": "IBAN_CODE", "CARD": "CREDIT_CARD",
         "ACC": "ACCOUNT_NUMBER", "AMT": "AMOUNT", "ORG": "ORGANIZATION", "CITY": "LOCATION",
         "EMPID": "EMPLOYEE_ID", "CLIENTID": "CLIENT_ID", "PROJ": "PROJECT_CODENAME"}
DIGIT_KINDS = {"NID", "PHONE", "CARD", "ACC", "AMT"}  # may be written with Arabic-Indic digits

# (lang, template, keys the task actually needs). {KIND} or {KIND#tag}; same key -> same value.
TEMPLATES = [
    ("en", "Customer {PERSON#a} (National ID {NID}) reports that the transfer of {AMT} to IBAN {IBAN} failed. "
           "Explain the common reasons a bank transfer fails.", []),
    ("en", "Draft a polite reply to {PERSON#a} confirming that card {CARD} has been blocked and that a "
           "replacement will be sent to the {CITY} branch.", ["PERSON#a", "CITY"]),
    ("en", "Summarize this KYC note: {PERSON#a}, phone {PHONE}, email {EMAIL}, employer {ORG}, monthly salary "
           "{AMT}, account {ACC}.", ["AMT"]),
    ("en", "Employee {EMPID} ({PERSON#a}) asked about the status of {PROJ}. Write a short status-update "
           "template for {PROJ}.", ["PROJ"]),
    ("en", "Is a loan of {AMT#a} affordable for someone earning {AMT#b} per month? Client {CLIENTID}, "
           "contact {PHONE}.", ["AMT#a", "AMT#b"]),
    ("en", "Hi team,\nPlease review the dispute raised by {PERSON#a} ({EMAIL}). The disputed charge of {AMT} "
           "appeared on card {CARD}. National ID on file: {NID}.\nThanks,\n{PERSON#b}", []),
    ("ar", "العميل {PERSON#a} (الرقم القومي {NID}) أبلغ أن التحويل بمبلغ {AMT} إلى الآيبان {IBAN} فشل. "
           "اشرح الأسباب الشائعة لفشل التحويلات البنكية.", []),
    ("ar", "اكتب رداً مهذباً على {PERSON#a} لتأكيد إيقاف البطاقة {CARD} وأن البطاقة البديلة ستصل إلى فرع {CITY}.",
     ["PERSON#a", "CITY"]),
    ("ar", "لخّص ملاحظة اعرف عميلك: {PERSON#a}، رقم الهاتف {PHONE}، البريد {EMAIL}، جهة العمل {ORG}، "
           "الراتب الشهري {AMT}، رقم الحساب {ACC}.", ["AMT"]),
    ("ar", "الموظف {EMPID} ({PERSON#a}) سأل عن حالة {PROJ}. اكتب نموذجاً مختصراً لتحديث حالة {PROJ}.", ["PROJ"]),
    ("ar", "هل قرض بقيمة {AMT#a} مناسب لشخص دخله {AMT#b} شهرياً؟ رقم العميل {CLIENTID}، للتواصل {PHONE}.",
     ["AMT#a", "AMT#b"]),
    ("ar", "تحية طيبة، يرجى مراجعة النزاع المقدم من {PERSON#a} ({EMAIL}) بخصوص خصم {AMT} على البطاقة {CARD}. "
           "الرقم القومي المسجل: {NID}.", []),
    ("mix", "Please check حساب {PERSON#a} رقم {ACC} وراجع التحويل بقيمة {AMT}.", []),
    ("mix", "العميل {PERSON#a} asked for a statement. IBAN {IBAN}, mobile {PHONE}.", []),
]
PH = re.compile(r"\{([A-Z]+)(?:#(\w+))?\}")


# ---------------------------------------------------------------- validators
def norm_digits(s):
    return re.sub(r"[\s\-+]", "", s.translate(EN_DIGITS))

def luhn_ok(num):
    d = [int(c) for c in num][::-1]
    return (sum(d[0::2]) + sum(sum(divmod(2 * x, 10)) for x in d[1::2])) % 10 == 0

def iban_ok(iban):
    s = iban.replace(" ", "")
    if len(s) != 29 or not s.startswith("EG"):
        return False
    r = s[4:] + s[:4]
    return int("".join(str(int(c, 36)) for c in r)) % 97 == 1

def nid_ok(nid):
    """Structure only (century, birth date, governorate). The 14th check digit is NOT validated:
    I do not know a public check-digit algorithm, so the generator emits a random last digit."""
    n = norm_digits(nid)
    if len(n) != 14 or n[0] not in "23" or n[7:9] not in GOV_CODES:
        return False
    year = (1900 if n[0] == "2" else 2000) + int(n[1:3])
    try:
        datetime.date(year, int(n[3:5]), int(n[5:7]))
    except ValueError:
        return False
    return True


# ---------------------------------------------------------------- value makers
class Person:
    def __init__(self, rng, male=None):
        self.male = rng.random() < 0.5 if male is None else male
        first = rng.choice(MALE if self.male else FEMALE)
        parts = [first]
        if rng.random() < 0.5:
            parts.append(rng.choice(MALE))  # father's name
        parts.append(rng.choice(FAMILY))
        self.ar = " ".join(p[0] for p in parts)
        self.en = " ".join(p[1] for p in parts)
        self.email_local = (parts[0][1] + "." + parts[-1][1]).lower()


def make_nid(rng, male):
    year = rng.randint(1950, 2005)
    d = datetime.date(year, 1, 1) + datetime.timedelta(days=rng.randint(0, 364))
    serial3 = f"{rng.randint(0, 999):03d}"
    gender = rng.choice([1, 3, 5, 7, 9] if male else [0, 2, 4, 6, 8])
    return ("2" if year < 2000 else "3") + f"{year % 100:02d}{d.month:02d}{d.day:02d}" + \
        rng.choice(GOV_CODES) + serial3 + str(gender) + str(rng.randint(0, 9))

def make_card(rng):
    body = rng.choice(["4", "51", "52", "53", "54", "55"])
    body += "".join(str(rng.randint(0, 9)) for _ in range(15 - len(body)))
    d = [int(c) for c in body][::-1]
    total = sum(sum(divmod(2 * x, 10)) for x in d[0::2]) + sum(d[1::2])
    num = body + str((10 - total % 10) % 10)
    sep = rng.choice(["", " ", "-"])
    return sep.join(num[i:i + 4] for i in range(0, 16, 4))

def make_iban(rng):
    bban = "".join(str(rng.randint(0, 9)) for _ in range(25))  # 4 bank + 4 branch + 17 account
    check = 98 - int(bban + "1416" + "00") % 97  # E=14, G=16
    iban = f"EG{check:02d}{bban}"
    return " ".join(iban[i:i + 4] for i in range(0, 29, 4)) if rng.random() < 0.5 else iban

def make_phone(rng):
    n = rng.choice(["010", "011", "012", "015"]) + "".join(str(rng.randint(0, 9)) for _ in range(8))
    fmt = rng.choice(["local", "intl", "intl_spaced"])
    if fmt == "local":
        return n
    if fmt == "intl":
        return "+20" + n[1:]
    return f"+20 {n[1:4]} {n[4:7]} {n[7:]}"

def make_amount(rng, ar):
    n = rng.choice([5000, 12500, 20000, 35000, 75000, 150000, 250000, 1200000])
    return f"{n:,} جنيه" if ar else rng.choice([f"EGP {n:,}", f"{n:,} EGP"])


class Ctx:
    def __init__(self, rng, lang):
        self.rng, self.lang, self.cache, self.people = rng, lang, {}, {}
        self.ar_digits = lang in ("ar", "mix") and rng.random() < 0.5

    def person(self, key):
        if key not in self.people:
            p = Person(self.rng)
            use_ar = self.rng.random() < (0.75 if self.lang == "ar" else 0.5 if self.lang == "mix" else 0.0)
            self.people[key] = (p, use_ar)
        return self.people[key]

    def value(self, kind, key):
        if key in self.cache:
            return self.cache[key]
        r = self.rng
        if kind == "PERSON":
            p, use_ar = self.person(key)
            v = p.ar if use_ar else p.en
        elif kind == "EMAIL":
            p, _ = self.people.get("PERSON#a") or self.person("PERSON#a")
            v = f"{p.email_local}@{r.choice(['mail.example', 'nilehorizon.example'])}"
        elif kind == "NID":
            p, _ = self.people.get("PERSON#a") or self.person("PERSON#a")
            v = make_nid(r, p.male)
        elif kind == "PHONE":
            v = make_phone(r)
        elif kind == "IBAN":
            v = make_iban(r)
        elif kind == "CARD":
            v = make_card(r)
        elif kind == "ACC":
            v = "".join(str(r.randint(0, 9)) for _ in range(13))
        elif kind == "AMT":
            v = make_amount(r, self.lang == "ar" or (self.lang == "mix" and r.random() < 0.5))
        elif kind == "ORG":
            v = r.choice(ORGS)[0 if self.lang == "ar" else 1]
        elif kind == "CITY":
            v = r.choice(CITIES)[0 if self.lang == "ar" else 1]
        elif kind == "EMPID":
            v = f"{BANK_NAME_PREFIX}-{r.randint(0, 999999):06d}"
        elif kind == "CLIENTID":
            v = f"CL-{r.randint(0, 9999999):07d}"
        elif kind == "PROJ":
            v = r.choice(PROJECTS)[0 if self.lang == "ar" else 1]
        else:
            raise ValueError(kind)
        if kind in DIGIT_KINDS and self.ar_digits:
            v = v.translate(AR_DIGITS)
        self.cache[key] = v
        return v


def render(lang, template, needed, rng):
    ctx = Ctx(rng, lang)
    out, spans, pos, cur = [], [], 0, 0
    for m in PH.finditer(template):
        chunk = template[pos:m.start()]
        out.append(chunk)
        cur += len(chunk)
        kind, tag = m.group(1), m.group(2)
        key = kind if tag is None else f"{kind}#{tag}"
        val = ctx.value(kind, key)
        spans.append({"start": cur, "end": cur + len(val), "label": LABEL[kind], "text": val,
                      "key": key, "needed": key in needed})
        out.append(val)
        cur += len(val)
        pos = m.end()
    out.append(template[pos:])
    return "".join(out), spans


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=3000)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--out", default="eg_finance_pii.jsonl")
    a = ap.parse_args()
    rng = random.Random(a.seed)
    stats, bad = Counter(), Counter()
    with open(a.out, "w", encoding="utf-8") as f:
        for i in range(a.n):
            lang, tpl, needed = rng.choice(TEMPLATES)
            text, spans = render(lang, tpl, set(needed), rng)
            for s in spans:  # self-checks
                assert text[s["start"]:s["end"]] == s["text"]
                stats[s["label"]] += 1
                n = norm_digits(s["text"])
                if s["label"] == "CREDIT_CARD" and not luhn_ok(n):
                    bad["card"] += 1
                if s["label"] == "IBAN_CODE" and not iban_ok(s["text"]):
                    bad["iban"] += 1
                if s["label"] == "EG_NATIONAL_ID" and not nid_ok(s["text"]):
                    bad["nid"] += 1
            stats["lang:" + lang] += 1
            f.write(json.dumps({"id": i, "lang": lang, "text": text, "spans": spans}, ensure_ascii=False) + "\n")
    print("docs:", a.n, "| invalid identifiers:", dict(bad) or "none")
    for k, v in sorted(stats.items()):
        print(f"  {k:22s}{v}")


if __name__ == "__main__":
    main()
