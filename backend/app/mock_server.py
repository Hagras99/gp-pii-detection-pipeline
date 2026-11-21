"""
MOCK server for the API contract.  NOT the real pipeline.

Detection here is a few regexes plus a fixed name list, so the frontend can be built and demoed
against realistic JSON (Arabic-Indic digits, an Arabic prefix glued to a name, kept vs masked
entities, restore, errors) before the real detectors exist.

Run:   uvicorn app.mock_server:app --reload --port 8000
Docs:  http://localhost:8000/docs
Test hooks (frontend development):
  header  X-Mock-Error: 429   -> rate-limit error envelope
  header  X-Mock-Error: 502   -> LLM unavailable error envelope
  env     MOCK_LLM_DELAY_S    -> simulated LLM latency (default 0.4)
  env     CORS_ORIGINS        -> comma-separated list (default: Vite and CRA dev servers)
"""
from __future__ import annotations

import asyncio
import os
import re
import time
import uuid
from collections import Counter
from typing import Optional

from fastapi import FastAPI, Header, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .schemas import (Action, ChatRequest, ChatResponse, DetectionSource, Entity, EntityType, ErrorBody,
                      ErrorResponse, GuardReport, HealthResponse, LatencyMs, Options, ReplacementKind,
                      SanitizeRequest, SanitizeResponse)

EN_DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")  # same length -> offsets are preserved
MOCK_NAMES = ["Mona Adel", "Ahmed Hassan", "Mohamed Ali", "منى عادل", "أحمد حسن", "محمد علي"]
FAKE_AR = ["سارة حسن", "كريم فهمي", "ياسمين منصور"]
FAKE_EN = ["Nour Mansour", "Omar Fahmy", "Hoda Soliman"]
ARABIC = re.compile(r"[\u0600-\u06FF]")

PATTERNS = [
    (EntityType.EG_NATIONAL_ID, re.compile(r"(?<!\d)\d{14}(?!\d)"), 0.99),
    (EntityType.EMAIL_ADDRESS, re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"), 0.99),
    (EntityType.PHONE_NUMBER, re.compile(r"(?<!\d)(?:\+20|0)1[0125]\d{8}(?!\d)"), 0.95),
    (EntityType.AMOUNT, re.compile(r"(?<![\d,])\d[\d,]*\s?(?:EGP|جنيه)|EGP\s?\d[\d,]*"), 0.90),
]


class ApiError(Exception):
    def __init__(self, status: int, code: str, message: str, retry_after_s: Optional[int] = None):
        self.status, self.code, self.message, self.retry_after_s = status, code, message, retry_after_s


app = FastAPI(title="PII Gateway API (MOCK)", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "http://localhost:5173,http://localhost:3000").split(","),
    allow_methods=["*"], allow_headers=["*"],
)


def _error(status: int, code: str, message: str, retry_after_s=None, details=None) -> JSONResponse:
    body = ErrorResponse(error=ErrorBody(code=code, message=message, retry_after_s=retry_after_s, details=details))
    headers = {"Retry-After": str(retry_after_s)} if retry_after_s else None
    return JSONResponse(status_code=status, content=body.model_dump(mode="json"), headers=headers)


@app.exception_handler(ApiError)
async def _api_error(_: Request, exc: ApiError):
    return _error(exc.status, exc.code, exc.message, exc.retry_after_s)


@app.exception_handler(RequestValidationError)
async def _validation_error(_: Request, exc: RequestValidationError):
    details = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in jsonable_encoder(exc.errors())]
    return _error(422, "invalid_request", "Request body failed validation.", details=details)


# ----------------------------------------------------------------------------- mock pipeline
def _ms(t0: float) -> float:
    return round((time.perf_counter() - t0) * 1000, 3)


def _detect(prompt: str):
    normalized = prompt.translate(EN_DIGITS)
    assert len(normalized) == len(prompt)
    found = []
    for etype, rx, score in PATTERNS:
        for m in rx.finditer(normalized):
            found.append((m.start(), m.end(), etype, DetectionSource.rules, score))
    for name in MOCK_NAMES:
        for m in re.finditer(re.escape(name), prompt):
            found.append((m.start(), m.end(), EntityType.PERSON, DetectionSource.ner, 0.88))
    found.sort(key=lambda s: (s[0], -(s[1] - s[0])))
    merged, last_end = [], -1
    for s in found:  # greedy: earliest, then longest; drop overlaps
        if s[0] >= last_end:
            merged.append(s)
            last_end = s[1]
    return merged


def _process(prompt: str, options: Options):
    t = time.perf_counter(); norm_ms = _ms(t)
    t = time.perf_counter(); spans = _detect(prompt); detect_ms = _ms(t)

    t = time.perf_counter()
    actions = [Action.keep if (s[2] == EntityType.AMOUNT and options.decide_mode == "task_aware") else Action.mask
               for s in spans]
    decide_ms = _ms(t)

    t = time.perf_counter()
    counters: Counter = Counter()
    seen: dict = {}
    n_fake = 0
    entities, out, pos = [], [], 0
    for i, ((start, end, etype, source, score), action) in enumerate(zip(spans, actions), 1):
        text = prompt[start:end]
        rep = kind = None
        if action == Action.mask:
            key = (etype, text)
            if key not in seen:
                pool = (FAKE_AR if ARABIC.search(text) else FAKE_EN) if etype == EntityType.PERSON else []
                cands = [n for n in pool if n not in prompt]  # collision check: a fake must not occur in the prompt
                if etype == EntityType.PERSON and options.name_strategy == "pseudonym" and cands:
                    seen[key] = (cands[n_fake % len(cands)], ReplacementKind.pseudonym)
                    n_fake += 1
                else:
                    counters[etype] += 1
                    seen[key] = (f"<{etype.value}_{counters[etype]}>", ReplacementKind.placeholder)
            rep, kind = seen[key]
        entities.append(Entity(id=f"e{i}", start=start, end=end, text=text, type=etype, source=source,
                               score=score, action=action, replacement=rep, replacement_kind=kind))
        out.append(prompt[pos:start]); out.append(rep if rep is not None else text); pos = end
    out.append(prompt[pos:])
    replace_ms = _ms(t)

    latency = dict(normalize=norm_ms, tier1=detect_ms, tier2=0.0, tier3=0.0, merge=0.0,
                   decide=decide_ms, replace=replace_ms)
    return "".join(out), entities, latency


def _restore(masked_answer: str, entities: list[Entity]) -> str:
    pairs = {e.replacement: e.text for e in entities if e.replacement}
    for rep in sorted(pairs, key=len, reverse=True):
        masked_answer = masked_answer.replace(rep, pairs[rep])
    return masked_answer


def _mock_llm(sanitized: str, entities: list[Entity]) -> str:
    persons = [e.replacement for e in entities if e.type == EntityType.PERSON and e.replacement]
    greeting = f"Dear {persons[0]}, " if persons else ""
    return f'{greeting}[MOCK LLM] I received your request: "{sanitized[:160]}"'


MOCK_WARNING = "MOCK: regex-only detection and a fixed name list. This is not the real pipeline."


# ----------------------------------------------------------------------------- endpoints
@app.get("/v1/health", response_model=HealthResponse)
def health():
    return HealthResponse(mode="mock")


@app.post("/v1/sanitize", response_model=SanitizeResponse)
def sanitize(req: SanitizeRequest):
    t0 = time.perf_counter()
    sanitized, entities, lat = _process(req.prompt, req.options)
    return SanitizeResponse(request_id=uuid.uuid4().hex, sanitized_prompt=sanitized, entities=entities,
                            latency_ms=LatencyMs(**lat, total=_ms(t0)), warnings=[MOCK_WARNING])


@app.post("/v1/chat", response_model=ChatResponse)
async def chat(req: ChatRequest, x_mock_error: Optional[str] = Header(default=None)):
    if x_mock_error == "429":
        raise ApiError(429, "rate_limited", "The LLM provider rate limit was reached. Try again later.", 20)
    if x_mock_error == "502":
        raise ApiError(502, "llm_unavailable", "The LLM provider did not respond.")
    t0 = time.perf_counter()
    sanitized, entities, lat = _process(req.prompt, req.options)

    t = time.perf_counter()
    await asyncio.sleep(float(os.getenv("MOCK_LLM_DELAY_S", "0.4")))
    masked_answer = _mock_llm(sanitized, entities)
    llm_ms = _ms(t)

    t = time.perf_counter()
    restored = _restore(masked_answer, entities)
    gr_ms = _ms(t)

    return ChatResponse(
        request_id=uuid.uuid4().hex, sanitized_prompt=sanitized, entities=entities,
        latency_ms=LatencyMs(**lat, llm=llm_ms, guard_restore=gr_ms, total=_ms(t0)),
        warnings=[MOCK_WARNING], model=req.model or "mock-llm",
        llm_response_masked=masked_answer, llm_response_restored=restored, guard=GuardReport())
