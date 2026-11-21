"""Local, single-turn privacy gateway demo."""
import re
from collections import Counter
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from .pipeline.tier1_rules import Tier1Rules
from .schemas import EntityType

app = FastAPI(title="PII Gateway PoC")
rules = Tier1Rules()
token_pattern = re.compile(r"<[A-Z_]+_\d+>")


class Prompt(BaseModel):
    prompt: str = Field(min_length=1, max_length=20_000)


def demo_provider(sanitized_prompt: str) -> str:
    return f"Demo provider received:\n{sanitized_prompt}"


@app.get("/")
def index():
    return FileResponse(Path(__file__).parent / "static" / "index.html")


@app.post("/poc/run")
def run(request: Prompt):
    prompt = request.prompt
    counts = Counter()
    reserved = set(token_pattern.findall(prompt))
    replacements = {}
    restore = {}
    entities = []
    parts = []
    cursor = 0
    for span in rules.detect(prompt):
        original = prompt[span.start:span.end]
        kind = span.type
        key = (kind, original)
        if key not in replacements:
            while True:
                counts[kind] += 1
                token = f"<{kind.value}_{counts[kind]}>"
                if token not in reserved:
                    break
            replacements[key] = token
            if kind == EntityType.EMAIL_ADDRESS:
                restore[token] = original
        token = replacements[key]
        parts.extend((prompt[cursor:span.start], token))
        cursor = span.end
        entities.append({"type": kind, "replacement": token})

    parts.append(prompt[cursor:])
    sanitized = "".join(parts)
    provider_reply = demo_provider(sanitized)
    return {
        "sanitized_prompt": sanitized,
        "provider_reply": provider_reply,
        "local_reply": token_pattern.sub(lambda match: restore.get(match[0], match[0]), provider_reply),
        "entities": entities,
    }
