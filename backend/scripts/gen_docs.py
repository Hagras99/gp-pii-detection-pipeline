"""Generate docs/API_CONTRACT.md with examples captured from the running mock (so they never drift)."""
import json, os, pathlib, sys
os.environ["MOCK_LLM_DELAY_S"] = "0"
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402
from app.mock_server import app  # noqa: E402

c = TestClient(app)
docs = pathlib.Path(__file__).resolve().parents[2] / "docs"
AR = "هل قرض بقيمة 250,000 جنيه مناسب لمنى عادل التي دخلها 20,000 جنيه؟ الرقم القومي ٢٩٠٠١٠١٠١٢٣٤٤٦."
req = {"prompt": AR, "options": {"name_strategy": "placeholder", "decide_mode": "task_aware"}}
chat = c.post("/v1/chat", json=req).json()
err = c.post("/v1/chat", json={"prompt": "hi"}, headers={"X-Mock-Error": "429"}).json()
for name, obj in (("chat_request", req), ("chat_response", chat), ("error_429", err)):
    (docs / "examples" / f"{name}.json").write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
j = lambda o: "```json\n" + json.dumps(o, indent=2, ensure_ascii=False) + "\n```"

md = f"""# PII Gateway API contract v0.1.0

The frontend and the backend both build against this file. The authoritative definitions are the Pydantic
models in `backend/app/schemas.py`; `docs/openapi.json` is generated from them. Changing the contract means
changing `schemas.py`, the tests, and bumping the version, in one pull request.

## Endpoints

| Method | Path | Purpose |
|---|---|---|
| GET | `/v1/health` | Liveness, and whether the server is `mock` or `live`. |
| POST | `/v1/sanitize` | Detect and replace only. No LLM call. Used by the evaluation harness and a "preview" button. |
| POST | `/v1/chat` | Full flow: sanitize, call the LLM, guard, restore. |

## Rules the frontend must follow

1. **Offsets.** `start`/`end` are character offsets into the *original* prompt (`end` exclusive). Each entity also
   carries `text`, so check `prompt.slice(start, end) === text`. They agree between Python and JavaScript for Arabic and
   Latin text; they would differ only for characters outside the Basic Multilingual Plane (such as emoji).
2. **Order.** Entities are sorted by `start` and never overlap.
3. **Actions.** `mask` means `replacement` and `replacement_kind` are set. `keep` means the value is sent to the LLM
   unchanged and both are `null`.
4. **Show both answers.** `llm_response_restored` is what the user reads; `llm_response_masked` is what the LLM
   really returned. Showing both is the demo.
5. **Errors** always use the envelope below. `429` includes `retry_after_s` and a `Retry-After` header.
6. **Options.** `name_strategy` (`placeholder` | `pseudonym`) is the project's A/B experiment. `decide_mode`
   (`task_aware` | `mask_all`) is an ablation switch. Expose both as toggles.
7. **Never store raw prompts in the browser** (localStorage and similar) in the real build.

## Example: `POST /v1/chat`

Request:
{j(req)}

Response (from the mock; the real server returns the same shape):
{j(chat)}

Note the Arabic prefix: the original text is "لمنى عادل" and the sanitized text is "ل<PERSON_1>". The replacement covers
only the name, so the glued preposition survives.

## Example: error

{j(err)}

## Entity types

`PERSON, EG_NATIONAL_ID, PHONE_NUMBER, EMAIL_ADDRESS, IBAN_CODE, CREDIT_CARD, ACCOUNT_NUMBER, AMOUNT, ORGANIZATION,
LOCATION, EMPLOYEE_ID, CLIENT_ID, PROJECT_CODENAME, SECRET`

## Mock-only test hooks

* Header `X-Mock-Error: 429` or `502` on `/v1/chat` returns that error. Use it to build the error states.
* Env `MOCK_LLM_DELAY_S` sets the simulated LLM delay (default 0.4 s). Use it to build loading states.
* Env `CORS_ORIGINS` is a comma-separated list (default: `http://localhost:5173,http://localhost:3000`).

## Generating TypeScript types

```
npx openapi-typescript docs/openapi.json -o src/api-types.ts
```
"""
(docs / "API_CONTRACT.md").write_text(md, encoding="utf-8")
print("wrote", docs / "API_CONTRACT.md")
