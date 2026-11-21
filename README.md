# PII Gateway

* Step 1: API contract, mock server, contract tests  (`docs/API_CONTRACT.md`)
* Step 2: span model, normalization with offset mapping, Tier 1 rules (regex + validators), merge policy,
  exact-match evaluator

```
cd backend
pip install -r requirements.txt
pytest                                                   # 29 tests
python tools/gen_eg_finance_pii.py --n 3000 --out eg_finance_pii.jsonl
python scripts/eval_tier1.py eg_finance_pii.jsonl         # Tier 1 exact-match scores + latency
uvicorn app.mock_server:app --reload --port 8000          # MOCK API for the frontend team
```

Layout: `app/schemas.py` (contract) | `app/pipeline/` (normalize, validators, spans, tier1_rules) |
`app/evaluation/metrics.py` | `app/mock_server.py` (MOCK, not the real pipeline) | `tools/` (synthetic data).

## Local browser proof of concept

From this folder, run:

```sh
cd backend
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python -m uvicorn app.poc:app
```

Open http://127.0.0.1:8000 and click **Load example** and **Run demo**.
The page shows the sanitized prompt, the reply from the local demo provider,
and the locally restored reply. This demo restores email addresses and keeps
the other detected values masked. Detection uses the existing Tier 1 rules.
