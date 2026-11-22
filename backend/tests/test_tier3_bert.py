import sys
from types import SimpleNamespace

from fastapi.testclient import TestClient

from app import main
from app.pipeline.spans import Span, resolve_overlaps
from app.pipeline.tier3_bert import MODEL_ID, WINDOW_OVERLAP, MultilingualBertDetector
from app.schemas import DetectionSource, EntityType


def test_tier3_keeps_tier2_label_for_identical_offsets():
    tier2 = Span(0, 12, EntityType.PERSON, DetectionSource.presidio, 0.85)
    tier3 = Span(0, 12, EntityType.ORGANIZATION, DetectionSource.ner, 0.99)
    assert resolve_overlaps([tier2, tier3]) == [tier2]


def test_demo_tier3_preserves_offsets_and_masks_and_restores(monkeypatch):
    # Include a Unicode prefix and put the entities beyond the first BERT window.
    prefix = "📌 " + "word " * 600
    prompt = prefix + "أرسل لسارة أحمد في Project Cedar عبر sara@example.com."
    tokenizer = SimpleNamespace(is_fast=True, model_max_length=10**30)
    classifier = SimpleNamespace(config=SimpleNamespace(max_position_embeddings=512))

    def cached_model(model, *, local_files_only):
        assert (model, local_files_only) == (MODEL_ID, True)
        return "cached-model"

    def load_tokenizer(model, *, use_fast, local_files_only, fix_mistral_regex):
        assert (model, use_fast, local_files_only, fix_mistral_regex) == ("cached-model", True, True, False)
        return tokenizer

    def load_model(model, *, use_safetensors, local_files_only):
        assert (model, use_safetensors, local_files_only) == ("cached-model", True, True)
        return classifier

    def pipeline(task, **kwargs):
        assert task == "token-classification"
        assert kwargs["tokenizer"].model_max_length == 512
        assert kwargs["stride"] == WINDOW_OVERLAP
        assert kwargs["aggregation_strategy"] == "simple"
        return classify

    def classify(text):
        assert text == prompt
        return [
            {"entity_group": group, "start": text.index(value),
             "end": text.index(value) + len(value), "score": 0.999}
            for group, value in (
                ("PER", "سارة أحمد"), ("ORG", "Project Cedar"), ("PER", "sara@example.com"),
            )
        ]

    monkeypatch.setitem(sys.modules, "huggingface_hub", SimpleNamespace(snapshot_download=cached_model))
    monkeypatch.setitem(sys.modules, "transformers", SimpleNamespace(
        AutoTokenizer=SimpleNamespace(from_pretrained=load_tokenizer),
        AutoModelForTokenClassification=SimpleNamespace(from_pretrained=load_model),
        pipeline=pipeline,
    ))
    monkeypatch.delenv("PII_TIER3_MODEL", raising=False)
    monkeypatch.delenv("PII_TIER3_ENABLED", raising=False)
    monkeypatch.setenv("PII_TIER2_ENABLED", "0")
    monkeypatch.setenv("PII_ORG_TERMS", "Project Cedar")
    assert len(main.build_detectors()) == 2

    monkeypatch.setenv("PII_TIER3_ENABLED", "1")
    detectors = main.build_detectors()
    assert isinstance(detectors[-1].__self__, MultilingualBertDetector)
    monkeypatch.setattr(main, "detectors", detectors)
    response = TestClient(main.app).post("/poc/run", json={"prompt": prompt})
    assert response.status_code == 200
    result = response.json()
    sanitized = prefix + "أرسل ل<PERSON_1> في <PROJECT_CODENAME_1> عبر <EMAIL_ADDRESS_1>."
    assert result["sanitized_prompt"] == sanitized
    assert result["provider_reply"] == f"Demo provider received:\n{sanitized}"
    assert result["local_reply"] == f"Demo provider received:\n{prompt}"
