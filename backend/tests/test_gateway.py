import pytest
from fastapi.testclient import TestClient

from app import main
from app.pipeline.gateway import run_gateway
from app.pipeline.spans import Span
from app.schemas import DetectionSource, EntityType


def test_arabic_phone_restored_in_original_digits_only_after_provider_reply():
    number = "٠١٠١٢٣٤٥٦٧٨"

    def provider(prompt):
        assert prompt == "اتصل على <PHONE_NUMBER_1>."
        return "رقم التواصل: <PHONE_NUMBER_1>"

    result = run_gateway(f"اتصل على {number}.", provider)

    assert result["provider_reply"] == "رقم التواصل: <PHONE_NUMBER_1>"
    assert result["local_reply"] == f"رقم التواصل: {number}"


def test_configured_terms_masked_without_matching_inside_other_words():
    from app.pipeline.lexicon import OrganizationLexicon
    from app.pipeline.tier1_rules import Tier1Rules

    lexicon = OrganizationLexicon(["Project Cedar", "مشروع النيل"])
    result = run_gateway(
        "project cedar و مشروع النيل. Project Cedarwood. mona@example.com",
        lambda text: text,
        (Tier1Rules().detect, lexicon.detect),
    )

    assert result["sanitized_prompt"] == (
        "<PROJECT_CODENAME_1> و <PROJECT_CODENAME_2>. Project Cedarwood. <EMAIL_ADDRESS_1>"
    )
    assert result["local_reply"] == "project cedar و مشروع النيل. Project Cedarwood. mona@example.com"


@pytest.mark.parametrize("enabled", [False, True])
def test_demo_tier2_opt_in_keeps_tier1_lexicon_and_restoration(monkeypatch, enabled):
    class StubPresidio:
        def __init__(self, model):
            assert enabled and model == "test_model"

        def detect(self, prompt):
            name = prompt.index("Jane Smith")
            project = prompt.index("Project Cedar")
            return [
                Span(name, name + len("Jane Smith"), EntityType.PERSON, DetectionSource.presidio, 0.85),
                Span(project, project + len("Project Cedar"), EntityType.PERSON, DetectionSource.presidio, 0.85),
            ]

    monkeypatch.setattr(main, "PresidioDetector", StubPresidio)
    monkeypatch.setenv("PII_TIER2_ENABLED", "1" if enabled else "0")
    monkeypatch.setenv("PII_TIER2_MODEL", "test_model")
    monkeypatch.setenv("PII_ORG_TERMS", "Project Cedar")
    monkeypatch.setattr(main, "detectors", main.build_detectors())

    prompt = "📌 Contact Jane Smith about Project Cedar at jane.smith@example.com."
    response = TestClient(main.app).post("/poc/run", json={"prompt": prompt})
    assert response.status_code == 200
    result = response.json()
    name = "<PERSON_1>" if enabled else "Jane Smith"
    sanitized = f"📌 Contact {name} about <PROJECT_CODENAME_1> at <EMAIL_ADDRESS_1>."
    assert result["sanitized_prompt"] == sanitized
    assert result["provider_reply"] == f"Demo provider received:\n{sanitized}"
    assert result["local_reply"] == f"Demo provider received:\n{prompt}"
