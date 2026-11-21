"""Run Tier 1 over a synthetic JSONL file and print exact-match scores plus latency."""
import json, pathlib, statistics, sys, time
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from app.evaluation.metrics import score_exact  # noqa: E402
from app.pipeline.tier1_rules import Tier1Rules  # noqa: E402
from app.schemas import EntityType  # noqa: E402

path = sys.argv[1] if len(sys.argv) > 1 else "eg_finance_pii.jsonl"
CUSTOM = {EntityType.EMPLOYEE_ID: r"(?<![A-Za-z0-9])NHB-\d{6}(?!\d)", EntityType.CLIENT_ID: r"(?<![A-Za-z0-9])CL-\d{7}(?!\d)"}
TARGET = {"EG_NATIONAL_ID", "CREDIT_CARD", "IBAN_CODE", "PHONE_NUMBER", "EMAIL_ADDRESS", "ACCOUNT_NUMBER",
          "EMPLOYEE_ID", "CLIENT_ID"}
det, gold, pred, lat = Tier1Rules(CUSTOM), {}, {}, []
for line in open(path, encoding="utf-8"):
    d = json.loads(line)
    gold[d["id"]] = [(s["start"], s["end"], s["label"]) for s in d["spans"]]
    t = time.perf_counter()
    spans = det.detect(d["text"])
    lat.append((time.perf_counter() - t) * 1000)
    pred[d["id"]] = [(s.start, s.end, s.type.value) for s in spans]
res = score_exact(gold, pred, TARGET)
print(f"{'type':16}{'tp':>6}{'fp':>5}{'fn':>5}{'P':>8}{'R':>8}{'F1':>8}")
for t in sorted(k for k in res if k != "MICRO") + ["MICRO"]:
    r = res[t]
    print(f"{t:16}{r['tp']:>6}{r['fp']:>5}{r['fn']:>5}{r['precision']:>8.3f}{r['recall']:>8.3f}{r['f1']:>8.3f}")
lat.sort()
print(f"\nTier 1 latency per prompt (this machine): median {statistics.median(lat):.3f} ms, p95 {lat[int(.95*len(lat))]:.3f} ms")
