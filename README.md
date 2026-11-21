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

## Module One ownership

| Owner | Implementation | Evaluation |
| --- | --- | --- |
| Project collaborator | Own the Tier 1 rules and multilingual detector integration. Add Presidio and multilingual BERT through the detector interface. | Run detector comparisons and report precision and recall by entity type and language. |
| Mostafa | Own the FastAPI gateway, browser demo, and masking and restoration workflow. | Write synthetic Arabic, English, and mixed-language prompts with expected outcomes. Verify the actual provider payload and local response. Record missed masks, incorrect restorations, and placeholder changes. |

Start the joint evaluation with the sample email and Egyptian mobile number.
Both must be masked in the provider input. The local reply should restore the
email under the demo policy and keep the phone masked. Once a real provider is
connected, repeat the checks with synthetic inputs and record whether the model
preserves placeholders and completes the task.
