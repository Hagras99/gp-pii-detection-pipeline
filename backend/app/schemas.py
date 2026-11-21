"""
API contract v0.1.0  --  the single source of truth for the frontend and the backend.

Rules every client must know
----------------------------
* `start` / `end` are CHARACTER offsets (Python str indices = Unicode code points) into the
  ORIGINAL prompt, `end` exclusive.  JavaScript strings count UTF-16 code units, so the two agree
  for Arabic and Latin text; they only differ for characters outside the Basic Multilingual Plane
  (e.g. emoji).  Every entity also carries `text`, so a client can verify `prompt.slice(start, end)`.
* Entities are sorted by `start` and never overlap.
* `action == "mask"` -> `replacement` and `replacement_kind` are set.
  `action == "keep"` -> both are null (the value is sent to the LLM unchanged).
* Every error response uses the `ErrorResponse` envelope.
"""
from __future__ import annotations

from enum import Enum
from typing import Literal, Optional

from pydantic import BaseModel, Field, model_validator

CONTRACT_VERSION = "0.1.0"


class EntityType(str, Enum):
    PERSON = "PERSON"
    EG_NATIONAL_ID = "EG_NATIONAL_ID"
    PHONE_NUMBER = "PHONE_NUMBER"
    EMAIL_ADDRESS = "EMAIL_ADDRESS"
    IBAN_CODE = "IBAN_CODE"
    CREDIT_CARD = "CREDIT_CARD"
    ACCOUNT_NUMBER = "ACCOUNT_NUMBER"
    AMOUNT = "AMOUNT"
    ORGANIZATION = "ORGANIZATION"
    LOCATION = "LOCATION"
    EMPLOYEE_ID = "EMPLOYEE_ID"
    CLIENT_ID = "CLIENT_ID"
    PROJECT_CODENAME = "PROJECT_CODENAME"
    SECRET = "SECRET"  # passwords, API keys: always masked, never a realistic fake


class DetectionSource(str, Enum):
    rules = "rules"          # Tier 1: regex + validators
    lexicon = "lexicon"      # Tier 1: organization term list
    presidio = "presidio"    # Tier 2
    ner = "ner"              # Tier 3


class Action(str, Enum):
    mask = "mask"
    keep = "keep"


class ReplacementKind(str, Enum):
    placeholder = "placeholder"   # e.g. <PERSON_1>
    pseudonym = "pseudonym"       # same-gender, same-script fake name (names only)


# ----------------------------------------------------------------------------- requests
class Options(BaseModel):
    name_strategy: Literal["placeholder", "pseudonym"] = Field(
        "placeholder", description="How PERSON entities are replaced (the project's A/B experiment).")
    decide_mode: Literal["task_aware", "mask_all"] = Field(
        "task_aware", description="task_aware: keep values the LLM needs. mask_all: mask every detected entity.")


class SanitizeRequest(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)
    query: Optional[str] = Field(
        None, max_length=5_000,
        description="The user's task, if separate from the prompt body. If omitted, the whole prompt is the query.")
    options: Options = Field(default_factory=Options)


class ChatRequest(SanitizeRequest):
    model: Optional[str] = Field(None, max_length=200, description="LLM id; the server default is used if omitted.")


# ----------------------------------------------------------------------------- responses
class Entity(BaseModel):
    id: str = Field(description="Stable within one response, e.g. 'e1'.")
    start: int = Field(ge=0)
    end: int = Field(gt=0)
    text: str = Field(description="The original text, equal to prompt[start:end].")
    type: EntityType
    source: DetectionSource
    score: float = Field(ge=0, le=1)
    action: Action
    replacement: Optional[str] = None
    replacement_kind: Optional[ReplacementKind] = None

    @model_validator(mode="after")
    def _check(self) -> "Entity":
        if self.end <= self.start:
            raise ValueError("end must be greater than start")
        if self.action == Action.mask and (self.replacement is None or self.replacement_kind is None):
            raise ValueError("masked entities need replacement and replacement_kind")
        if self.action == Action.keep and (self.replacement is not None or self.replacement_kind is not None):
            raise ValueError("kept entities must not have a replacement")
        return self


class LatencyMs(BaseModel):
    normalize: float = Field(ge=0)
    tier1: float = Field(ge=0)
    tier2: float = Field(ge=0)
    tier3: float = Field(ge=0)
    merge: float = Field(ge=0)
    decide: float = Field(ge=0)
    replace: float = Field(ge=0)
    llm: Optional[float] = Field(None, ge=0, description="null for /v1/sanitize")
    guard_restore: Optional[float] = Field(None, ge=0, description="null for /v1/sanitize")
    total: float = Field(ge=0)


class GuardReport(BaseModel):
    placeholders_repaired: int = Field(0, ge=0, description="Damaged placeholders the guard fixed before restoring.")
    placeholders_unresolved: list[str] = Field(default_factory=list, description="Placeholders it could not map back.")


class SanitizeResponse(BaseModel):
    request_id: str
    contract_version: str = CONTRACT_VERSION
    sanitized_prompt: str
    entities: list[Entity]
    latency_ms: LatencyMs
    warnings: list[str] = Field(default_factory=list)


class ChatResponse(SanitizeResponse):
    model: str
    llm_response_masked: str = Field(description="What the LLM actually returned (contains placeholders / fakes).")
    llm_response_restored: str = Field(description="The answer shown to the user, with real values restored.")
    guard: GuardReport = Field(default_factory=GuardReport)


class ErrorBody(BaseModel):
    code: Literal["invalid_request", "rate_limited", "llm_unavailable", "internal_error"]
    message: str
    retry_after_s: Optional[int] = None
    details: Optional[list[dict]] = None


class ErrorResponse(BaseModel):
    error: ErrorBody


class HealthResponse(BaseModel):
    status: Literal["ok"] = "ok"
    mode: Literal["mock", "live"]
    contract_version: str = CONTRACT_VERSION
