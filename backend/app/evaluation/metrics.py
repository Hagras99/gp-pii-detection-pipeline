"""Exact-match span metrics: a prediction counts only if (doc, start, end, type) all match the gold span."""
from __future__ import annotations

from collections import defaultdict


def prf(tp: int, fp: int, fn: int):
    p = tp / (tp + fp) if tp + fp else 0.0
    r = tp / (tp + fn) if tp + fn else 0.0
    return p, r, (2 * p * r / (p + r) if p + r else 0.0)


def score_exact(gold: dict, pred: dict, types: set[str]):
    """gold/pred: {doc_id: [(start, end, type_str), ...]}. Only `types` are scored."""
    counts = defaultdict(lambda: [0, 0, 0])  # type -> [tp, fp, fn]
    for doc in set(gold) | set(pred):
        g = {s for s in gold.get(doc, []) if s[2] in types}
        p = {s for s in pred.get(doc, []) if s[2] in types}
        for s in g & p:
            counts[s[2]][0] += 1
        for s in p - g:
            counts[s[2]][1] += 1
        for s in g - p:
            counts[s[2]][2] += 1
    out = {t: dict(zip(("tp", "fp", "fn"), c)) | dict(zip(("precision", "recall", "f1"), prf(*c))) for t, c in counts.items()}
    tp, fp, fn = (sum(c[i] for c in counts.values()) for i in range(3))
    out["MICRO"] = {"tp": tp, "fp": fp, "fn": fn, **dict(zip(("precision", "recall", "f1"), prf(tp, fp, fn)))}
    return out
