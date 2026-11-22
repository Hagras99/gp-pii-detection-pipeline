# PII Gateway

The gateway detects sensitive text, replaces it with placeholders before calling a local echo provider, and restores the original values in the local reply. The browser shows the sanitized prompt, provider reply, and restored reply. The demo needs no API keys.

## Quick start

From the repository root, enter `backend`. If you already have `backend/.venv`, skip the environment creation command.

```sh
cd backend
python3 -m venv .venv
./.venv/bin/python -m pip install -r requirements.txt
```

Create `backend/.env` using the example below, then run this from `backend`:

```sh
./.venv/bin/python -m uvicorn app.main:app --env-file .env --host 127.0.0.1 --port 8000
```

Open [the browser demo](http://127.0.0.1:8000/). Paste `راجع مشروع النيل وابعت الرد على mona@example.com` and click **Run demo**. With the example dictionary, **Sanitized prompt** should show `راجع <PROJECT_CODENAME_1> وابعت الرد على <EMAIL_ADDRESS_1>`. **Local reply** should include the original project name and email.

## Environment settings

Copy this starter configuration into `backend/.env`. The project names are examples. Both model-backed tiers are off so the base installation can start immediately.

```dotenv
PII_ORG_TERMS="Project Cedar,مشروع النيل,مشروع المهجرس"
PII_TIER2_ENABLED=0
PII_TIER2_MODEL=en_core_web_sm
PII_TIER3_ENABLED=0
PII_TIER3_MODEL=Davlan/bert-base-multilingual-cased-ner-hrl
```

| Setting | Default if omitted | What to put in it |
| --- | --- | --- |
| `PII_ORG_TERMS` | Empty | A comma-separated dictionary of project names, codenames, and aliases to mask. |
| `PII_TIER2_ENABLED` | Off | Set to `1` after installing the Tier 2 dependencies and model. |
| `PII_TIER2_MODEL` | `en_core_web_sm` | An installed English spaCy NER package or local model directory. |
| `PII_TIER3_ENABLED` | Off | Set to `1` after installing the Tier 3 dependencies and downloading the model. |
| `PII_TIER3_MODEL` | `Davlan/bert-base-multilingual-cased-ner-hrl` | The model ID if already downloaded into the Hugging Face cache, or the path to a local model directory. |

The organization dictionary matches literal phrases case-insensitively and masks them as `PROJECT_CODENAME`. Spaces within a name are allowed. List aliases, translations, and alternate spellings as separate entries. The dictionary accepts English and Arabic phrases. Keep private organization terms in your local, Git-ignored `.env`.

The app reads these settings at startup. Stop the server with `Ctrl+C` and restart it after changing `.env`. If a shell variable overrides a value in the file, unset that variable in the shell before restarting. Use an absolute model path or a path relative to the directory you launch from.

## Optional detector setup

### Tier 2 · English Presidio and spaCy

From `backend`, install [Microsoft Presidio Analyzer](https://pypi.org/project/presidio-analyzer/) and download the [English spaCy model](https://spacy.io/models/en):

```sh
./.venv/bin/python -m pip install -r requirements-tier2.txt
./.venv/bin/python -m spacy download en_core_web_sm
```

Set `PII_TIER2_ENABLED=1` and restart. Try `Please contact Jane Smith at jane.smith@example.com.` Tier 2 can add `<PERSON_1>` for the name. Tier 1 already masks the email.

### Tier 3 · Multilingual BERT

From `backend`, install the dependencies and download the required files from the [official Davlan model repository](https://huggingface.co/Davlan/bert-base-multilingual-cased-ner-hrl):

```sh
./.venv/bin/python -m pip install -r requirements-tier3.txt
./.venv/bin/hf download Davlan/bert-base-multilingual-cased-ner-hrl \
  config.json tokenizer_config.json special_tokens_map.json vocab.txt model.safetensors
```

The weights are about 709 MB. Set `PII_TIER3_ENABLED=1` and restart. If you already have the files in a local directory, set `PII_TIER3_MODEL` to that directory. For example, if they were installed under the virtual environment, use:

```dotenv
PII_TIER3_MODEL=.venv/share/pii-gateway/models/bert-base-multilingual-cased-ner-hrl
```

Tier 3 runs locally on CPU and can run with or without Tier 2. It uses overlapping token windows for long prompts. Try `The reviewer was Jean-Luc Picard, and the approver was Anne-Marie O’Neill.` With both optional tiers enabled, the verified result was `The reviewer was <PERSON_1>, and the approver was <PERSON_2>.`

## Detection and masking flow

1. `POST /poc/run` accepts a JSON object with a `prompt` string of 1–20,000 characters.
2. Tier 1 applies rules and validators to structured values such as email addresses and phone numbers. The organization lexicon adds configured project names. Optional Tier 2 adds English person and location candidates, and optional Tier 3 adds multilingual person, organization, and location candidates.
3. The gateway merges candidates using character offsets into the original prompt. Rules and lexicon matches take precedence over overlapping Tier 3 candidates. If Tier 2 and Tier 3 return identical boundaries, Tier 2 keeps its label. The remaining candidates are ranked by score, span length, and entity type.
4. The gateway sends the sanitized prompt to the echo provider. The response includes `sanitized_prompt`, `provider_reply`, `local_reply`, and `entities`. Restoration uses intact placeholders to recover the original formatting locally.

English spaCy has limited Arabic coverage. Multilingual BERT can still miss lowercase names or return partial Arabic spans when particles are attached. A successful demo example shows behavior for that prompt. Use labeled examples and exact spans to measure coverage.

## Tests and evaluation

Run the test suite from `backend`. The tests use synthetic inputs, with stubs for the optional models where needed.

```sh
./.venv/bin/python -m pytest -q
```

Generate synthetic Egyptian finance prompts and run the existing Tier 1 exact-span and latency benchmark:

```sh
./.venv/bin/python tools/gen_eg_finance_pii.py --n 3000 --out eg_finance_pii.jsonl
./.venv/bin/python scripts/eval_tier1.py eg_finance_pii.jsonl
```

## Repository guide

| Path | Responsibility |
| --- | --- |
| [backend/app/main.py](backend/app/main.py) | Browser demo and `/poc/run` entry point. Builds the configured detectors at startup. |
| [backend/app/pipeline/](backend/app/pipeline/) | Detectors, normalization and offset mapping, overlap handling, masking, and restoration. |
| [backend/app/static/index.html](backend/app/static/index.html) | Local browser interface. |
| [backend/app/mock_server.py](backend/app/mock_server.py) | Separate mock service implementing the [versioned API contract](docs/API_CONTRACT.md). |
| [backend/app/evaluation/](backend/app/evaluation/) | Exact-span scoring helpers. |
| [backend/tests/](backend/tests/) | Contract, detector, and gateway tests. |

To launch the separate contract mock, run `./.venv/bin/python -m uvicorn app.mock_server:app --port 8001` from `backend`.
