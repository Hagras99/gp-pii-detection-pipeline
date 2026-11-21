# PII Gateway API contract v0.1.0

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
```json
{
  "prompt": "هل قرض بقيمة 250,000 جنيه مناسب لمنى عادل التي دخلها 20,000 جنيه؟ الرقم القومي ٢٩٠٠١٠١٠١٢٣٤٤٦.",
  "options": {
    "name_strategy": "placeholder",
    "decide_mode": "task_aware"
  }
}
```

Response (from the mock; the real server returns the same shape):
```json
{
  "request_id": "7d3eaad6ba85409d90d424b930f8e8ec",
  "contract_version": "0.1.0",
  "sanitized_prompt": "هل قرض بقيمة 250,000 جنيه مناسب ل<PERSON_1> التي دخلها 20,000 جنيه؟ الرقم القومي <EG_NATIONAL_ID_1>.",
  "entities": [
    {
      "id": "e1",
      "start": 13,
      "end": 25,
      "text": "250,000 جنيه",
      "type": "AMOUNT",
      "source": "rules",
      "score": 0.9,
      "action": "keep",
      "replacement": null,
      "replacement_kind": null
    },
    {
      "id": "e2",
      "start": 33,
      "end": 41,
      "text": "منى عادل",
      "type": "PERSON",
      "source": "ner",
      "score": 0.88,
      "action": "mask",
      "replacement": "<PERSON_1>",
      "replacement_kind": "placeholder"
    },
    {
      "id": "e3",
      "start": 53,
      "end": 64,
      "text": "20,000 جنيه",
      "type": "AMOUNT",
      "source": "rules",
      "score": 0.9,
      "action": "keep",
      "replacement": null,
      "replacement_kind": null
    },
    {
      "id": "e4",
      "start": 79,
      "end": 93,
      "text": "٢٩٠٠١٠١٠١٢٣٤٤٦",
      "type": "EG_NATIONAL_ID",
      "source": "rules",
      "score": 0.99,
      "action": "mask",
      "replacement": "<EG_NATIONAL_ID_1>",
      "replacement_kind": "placeholder"
    }
  ],
  "latency_ms": {
    "normalize": 0.0,
    "tier1": 0.182,
    "tier2": 0.0,
    "tier3": 0.0,
    "merge": 0.0,
    "decide": 0.003,
    "replace": 0.044,
    "llm": 0.097,
    "guard_restore": 0.006,
    "total": 0.362
  },
  "warnings": [
    "MOCK: regex-only detection and a fixed name list. This is not the real pipeline."
  ],
  "model": "mock-llm",
  "llm_response_masked": "Dear <PERSON_1>, [MOCK LLM] I received your request: \"هل قرض بقيمة 250,000 جنيه مناسب ل<PERSON_1> التي دخلها 20,000 جنيه؟ الرقم القومي <EG_NATIONAL_ID_1>.\"",
  "llm_response_restored": "Dear منى عادل, [MOCK LLM] I received your request: \"هل قرض بقيمة 250,000 جنيه مناسب لمنى عادل التي دخلها 20,000 جنيه؟ الرقم القومي ٢٩٠٠١٠١٠١٢٣٤٤٦.\"",
  "guard": {
    "placeholders_repaired": 0,
    "placeholders_unresolved": []
  }
}
```

Note the Arabic prefix: the original text is "لمنى عادل" and the sanitized text is "ل<PERSON_1>". The replacement covers
only the name, so the glued preposition survives.

## Example: error

```json
{
  "error": {
    "code": "rate_limited",
    "message": "The LLM provider rate limit was reached. Try again later.",
    "retry_after_s": 20,
    "details": null
  }
}
```

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
