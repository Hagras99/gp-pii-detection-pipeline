"""Local multilingual token classification on the original prompt."""
from pathlib import Path

from ..schemas import DetectionSource, EntityType
from .spans import Span

MODEL_ID = "Davlan/bert-base-multilingual-cased-ner-hrl"
WINDOW_OVERLAP = 64
ENTITY_TYPES = {
    "PER": EntityType.PERSON,
    "ORG": EntityType.ORGANIZATION,
    "LOC": EntityType.LOCATION,
}


class MultilingualBertDetector:
    def __init__(self, model: str = MODEL_ID):
        try:
            from huggingface_hub import snapshot_download
            from transformers import AutoModelForTokenClassification, AutoTokenizer, pipeline
        except ImportError as exc:
            raise RuntimeError("Install requirements-tier3.txt before enabling Tier 3.") from exc

        try:
            model_dir = model if Path(model).is_dir() else snapshot_download(model, local_files_only=True)
            # Transformers 4.57 can misidentify this large BERT vocabulary as Mistral.
            tokenizer = AutoTokenizer.from_pretrained(
                model_dir, use_fast=True, local_files_only=True, fix_mistral_regex=False,
            )
            classifier = AutoModelForTokenClassification.from_pretrained(
                model_dir, local_files_only=True, use_safetensors=True,
            )
        except (OSError, ValueError) as exc:
            raise RuntimeError(f"Download the Tier 3 model files locally before enabling Tier 3: {model!r}") from exc
        if not tokenizer.is_fast:
            raise RuntimeError("Tier 3 requires a fast tokenizer for offsets and sliding windows.")
        tokenizer.model_max_length = min(tokenizer.model_max_length, classifier.config.max_position_embeddings)
        self.classify = pipeline(
            "token-classification",
            model=classifier,
            tokenizer=tokenizer,
            aggregation_strategy="simple",
            stride=WINDOW_OVERLAP,
            device=-1,
        )

    def detect(self, prompt: str) -> list[Span]:
        spans = []
        for result in self.classify(prompt):
            kind = ENTITY_TYPES.get(result["entity_group"])
            start, end = result["start"], result["end"]
            if kind is not None and start is not None and end is not None and 0 <= start < end <= len(prompt):
                spans.append(Span(start, end, kind, DetectionSource.ner, float(result["score"])))
        return spans
