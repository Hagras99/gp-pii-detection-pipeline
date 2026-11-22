"""Local, single-turn privacy gateway demo."""
import os
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .pipeline.gateway import run_gateway
from .pipeline.lexicon import OrganizationLexicon
from .pipeline.tier2_presidio import PresidioDetector
from .pipeline.tier1_rules import Tier1Rules
from .pipeline.tier3_bert import MODEL_ID, MultilingualBertDetector


def build_detectors():
    lexicon = OrganizationLexicon(os.getenv("PII_ORG_TERMS", "").split(","))
    detectors = (Tier1Rules().detect, lexicon.detect)
    if os.getenv("PII_TIER2_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}:
        model = os.getenv("PII_TIER2_MODEL", "en_core_web_sm")
        detectors += (PresidioDetector(model).detect,)
    if os.getenv("PII_TIER3_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}:
        model = os.getenv("PII_TIER3_MODEL", MODEL_ID)
        detectors += (MultilingualBertDetector(model).detect,)
    return detectors


app = FastAPI(title="PII Gateway PoC")
detectors = build_detectors()


class Prompt(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)


def demo_provider(sanitized_prompt: str) -> str:
    return f"Demo provider received:\n{sanitized_prompt}"


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.post("/poc/run")
def run(request: Prompt):
    return run_gateway(request.prompt, demo_provider, detectors)
