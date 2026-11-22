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
and the locally restored reply. The gateway restores all detected values locally, preserving their original
formatting when the provider returns their placeholders. Tier 1 rules run by default.

### Masking internal project names

Set `PII_ORG_TERMS` to a comma-separated list before starting the server:

```sh
PII_ORG_TERMS='Project Cedar,مشروع النيل,مشروع المهجرس' python -m uvicorn app.poc:app --reload
```

Try `راجع مشروع النيل وابعت الرد على mona@example.com`. The gateway sends
a project codename placeholder and an email placeholder. It restores both values
locally when their placeholders appear in the reply.

### Opt in to Tier 2 English detection

From `backend`, install [Microsoft Presidio Analyzer](https://pypi.org/project/presidio-analyzer/)
and the [English spaCy model](https://spacy.io/models/en):

```sh
.venv/bin/python -m pip install -r requirements-tier2.txt
.venv/bin/python -m spacy download en_core_web_sm
```

Start the demo with Tier 2 enabled:

```sh
PII_TIER2_ENABLED=1 .venv/bin/python -m uvicorn app.poc:app
```

If you already launch with `--env-file .env`, you can set `PII_TIER2_ENABLED=1`
in that file and restart with your usual command. Tier 2 defaults to off.
`PII_TIER2_MODEL` defaults to `en_core_web_sm` and accepts an installed English
spaCy NER package name or a local model directory. An enabled instance requires
the dependencies and model at startup. Inference runs locally.

Try `Please contact Jane Smith at jane.smith@example.com.` With Tier 2 off, the
email is masked. With Tier 2 on, the English name is also masked. Presidio adds
person and location candidates using offsets into the original prompt. The existing
overlap policy merges them with Tier 1 and organization lexicon matches. The echo
provider receives the masked prompt and the local reply restores the original values.

The English model has no reliable coverage for Arabic names and locations, including
in mixed-language prompts. Tier 1 rules and configured Arabic lexicon terms still
apply.

### Opt in to Tier 3 multilingual detection

From `backend`, install the optional dependencies and download the tokenizer,
config, and safetensors weights from the
[official Davlan model repository](https://huggingface.co/Davlan/bert-base-multilingual-cased-ner-hrl):

```sh
.venv/bin/python -m pip install -r requirements-tier3.txt
.venv/bin/hf download Davlan/bert-base-multilingual-cased-ner-hrl config.json tokenizer_config.json special_tokens_map.json vocab.txt model.safetensors
```

The weights are about 709 MB. Start the demo with Tier 2 and Tier 3 enabled
after completing the Tier 2 setup above:

```sh
PII_TIER2_ENABLED=1 PII_TIER3_ENABLED=1 .venv/bin/python -m uvicorn app.poc:app
```

Tier 3 defaults to off and can also run with Tier 2 off. It loads the downloaded
model from the local Hugging Face cache at startup. Set `PII_TIER3_MODEL` to the
model directory if you downloaded with `hf download --local-dir`. Inference
runs on the CPU using overlapping token windows, with character offsets into
the original prompt.

Tier 3 adds person, organization, and location candidates. Tier 1 rules and
organization lexicon matches take precedence over overlapping Tier 3 candidates.
When Tier 2 and Tier 3 return identical boundaries, the Tier 2 label takes
precedence. Other conflicts use the existing overlap ranking. The model supports Arabic and
English, but casing, punctuation, and attached Arabic particles can affect span
boundaries. Evaluate exact spans before relying on its coverage.
