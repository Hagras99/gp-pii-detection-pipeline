"""Single-turn masking, provider call, and local restoration."""
import re
from collections import Counter
from collections.abc import Callable

from .spans import Span, resolve_overlaps
from .tier1_rules import Tier1Rules

rules = Tier1Rules()
token_pattern = re.compile(r"<[A-Z_]+_\d+>")


def run_gateway(
    prompt: str,
    provider: Callable[[str], str],
    detectors: tuple[Callable[[str], list[Span]], ...] = (rules.detect,),
) -> dict:
    counts = Counter()
    reserved = set(token_pattern.findall(prompt))
    replacements = {}
    restore = {}
    entities = []
    parts = []
    cursor = 0
    candidates = [span for detect in detectors for span in detect(prompt)]
    for span in resolve_overlaps(candidates):
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
            restore[token] = original
        token = replacements[key]
        parts.extend((prompt[cursor:span.start], token))
        cursor = span.end
        entities.append({"type": kind, "replacement": token})

    parts.append(prompt[cursor:])
    sanitized = "".join(parts)
    provider_reply = provider(sanitized)
    return {
        "sanitized_prompt": sanitized,
        "provider_reply": provider_reply,
        "local_reply": token_pattern.sub(lambda match: restore.get(match[0], match[0]), provider_reply),
        "entities": entities,
    }
