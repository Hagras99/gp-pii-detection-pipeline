"""Local English named-entity detection through Presidio Analyzer."""
from pathlib import Path

from ..schemas import DetectionSource, EntityType
from .spans import Span

ENTITIES = [EntityType.PERSON.value, EntityType.LOCATION.value]


class PresidioDetector:
    def __init__(self, model: str):
        # Keep the baseline usable without the optional dependencies.
        try:
            from presidio_analyzer import AnalyzerEngine
            from presidio_analyzer.nlp_engine import SpacyNlpEngine
            from spacy.util import is_package
        except ImportError as exc:
            raise RuntimeError("Install requirements-tier2.txt before enabling Tier 2.") from exc

        # Presidio can auto-download missing models. Require a local install.
        if not model or not (is_package(model) or Path(model).is_dir()):
            raise RuntimeError(f"Install the local English spaCy model {model!r} before enabling Tier 2.")

        engine = SpacyNlpEngine(models=[{"lang_code": "en", "model_name": model}])
        engine.load()
        pipeline = engine.nlp["en"]
        if pipeline.lang != "en" or "ner" not in pipeline.pipe_names:
            raise RuntimeError("PII_TIER2_MODEL must be an English spaCy pipeline with an NER component.")
        self.analyzer = AnalyzerEngine(nlp_engine=engine, supported_languages=["en"])

    def detect(self, prompt: str) -> list[Span]:
        results = self.analyzer.analyze(text=prompt, language="en", entities=ENTITIES)
        return [
            Span(result.start, result.end, EntityType(result.entity_type), DetectionSource.presidio, result.score)
            for result in results
        ]
