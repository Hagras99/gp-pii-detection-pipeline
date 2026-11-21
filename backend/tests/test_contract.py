"""Contract tests: they pin the behaviour the frontend relies on. The real backend must pass them too."""
import os

os.environ["MOCK_LLM_DELAY_S"] = "0"

from fastapi.testclient import TestClient  # noqa: E402

from app.mock_server import app  # noqa: E402
from app.schemas import ChatResponse, SanitizeResponse  # noqa: E402

client = TestClient(app)
AR = "هل قرض بقيمة 250,000 جنيه مناسب لمنى عادل التي دخلها 20,000 جنيه؟ الرقم القومي ٢٩٠٠١٠١٠١٢٣٤٤٦."
EN = "Is a loan of EGP 250,000 affordable for Mona Adel? Email mona@mail.example, phone +201012345678."


def post(path, prompt, **opts):
    return client.post(path, json={"prompt": prompt, "options": opts})


def test_health():
    r = client.get("/v1/health")
    assert r.status_code == 200 and r.json()["mode"] == "mock"


def test_offsets_match_text_sorted_and_non_overlapping():
    for prompt in (AR, EN):
        body = post("/v1/sanitize", prompt).json()
        SanitizeResponse.model_validate(body)
        ents = body["entities"]
        assert ents, "mock should detect something"
        assert all(prompt[e["start"]:e["end"]] == e["text"] for e in ents)
        assert all(a["end"] <= b["start"] for a, b in zip(ents, ents[1:]))


def test_arabic_indic_id_is_detected_and_hidden():
    body = post("/v1/sanitize", AR).json()
    ids = [e for e in body["entities"] if e["type"] == "EG_NATIONAL_ID"]
    assert len(ids) == 1 and ids[0]["action"] == "mask"
    assert ids[0]["text"] not in body["sanitized_prompt"]


def test_arabic_prefix_stays_attached_to_replacement():
    body = post("/v1/sanitize", AR, name_strategy="placeholder").json()
    assert "ل<PERSON_1>" in body["sanitized_prompt"]


def test_task_aware_keeps_amounts_and_mask_all_masks_them():
    kept = post("/v1/sanitize", AR).json()
    assert "250,000 جنيه" in kept["sanitized_prompt"]
    amounts = [e for e in kept["entities"] if e["type"] == "AMOUNT"]
    assert amounts and all(e["action"] == "keep" and e["replacement"] is None for e in amounts)
    masked = post("/v1/sanitize", AR, decide_mode="mask_all").json()
    assert "250,000 جنيه" not in masked["sanitized_prompt"] and "<AMOUNT_1>" in masked["sanitized_prompt"]


def test_name_strategies():
    ph = post("/v1/sanitize", EN, name_strategy="placeholder").json()
    ps = post("/v1/sanitize", EN, name_strategy="pseudonym").json()
    p1 = next(e for e in ph["entities"] if e["type"] == "PERSON")
    p2 = next(e for e in ps["entities"] if e["type"] == "PERSON")
    assert p1["replacement"] == "<PERSON_1>" and p1["replacement_kind"] == "placeholder"
    assert p2["replacement_kind"] == "pseudonym" and p2["replacement"] != p2["text"]


def test_chat_restores_real_values_and_masked_answer_leaks_nothing():
    for strategy in ("placeholder", "pseudonym"):
        body = post("/v1/chat", AR, name_strategy=strategy).json()
        ChatResponse.model_validate(body)
        assert "٢٩٠٠١٠١٠١٢٣٤٤٦" not in body["llm_response_masked"]
        assert "منى عادل" not in body["llm_response_masked"]
        assert "<PERSON_1>" not in body["llm_response_restored"]
        assert body["guard"]["placeholders_unresolved"] == []
        assert body["latency_ms"]["llm"] is not None and body["latency_ms"]["total"] >= 0


def test_entity_invariants():
    for e in post("/v1/sanitize", AR + " " + EN).json()["entities"]:
        if e["action"] == "mask":
            assert e["replacement"] and e["replacement_kind"]
        else:
            assert e["replacement"] is None and e["replacement_kind"] is None


def test_validation_error_uses_envelope():
    r = client.post("/v1/sanitize", json={"prompt": ""})
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "invalid_request" and r.json()["error"]["details"]


def test_simulated_errors():
    r = client.post("/v1/chat", json={"prompt": "hi"}, headers={"X-Mock-Error": "429"})
    assert r.status_code == 429 and r.json()["error"]["retry_after_s"] == 20 and r.headers["Retry-After"] == "20"
    r = client.post("/v1/chat", json={"prompt": "hi"}, headers={"X-Mock-Error": "502"})
    assert r.status_code == 502 and r.json()["error"]["code"] == "llm_unavailable"


def test_unknown_option_value_rejected():
    assert post("/v1/sanitize", "hi", name_strategy="nope").status_code == 422
