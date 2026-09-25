"""
tests/test_voice_correction.py
-------------------------------
Tests for voice transcript correction and the interpreted_text field.
Derived from scripts/test_voice_correction.py.
Calls Gemini → marked integration.
"""

import pytest

pytestmark = pytest.mark.integration

EXPECTED_RESPONSE_FIELDS = [
    "query_id", "sql", "explanation", "confidence",
    "needs_clarification", "clarification_question",
    "query_type", "result", "chart_type", "interpreted_text",
]


def _query(client, session_id, text):
    return client.post("/api/query", json={
        "session_id": session_id,
        "text": text,
        "language": "auto",
    })


# ---------------------------------------------------------------------------
# Contract: response shape
# ---------------------------------------------------------------------------

class TestResponseContract:
    def test_all_expected_fields_present(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "shom me pashents older then fourty")
        assert resp.status_code == 200
        data = resp.json()
        for field in EXPECTED_RESPONSE_FIELDS:
            assert field in data, f"Missing field: {field}"


# ---------------------------------------------------------------------------
# Misheard / misspelled voice input
# ---------------------------------------------------------------------------

class TestVoiceTranscriptCorrection:
    def test_misheard_query_returns_200(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "shom me pashents older then fourty")
        assert resp.status_code == 200

    def test_misheard_query_interpreted_text_resolved(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "shom me pashents older then fourty")
        data = resp.json()
        interpreted = data.get("interpreted_text", "").lower()
        assert "patients" in interpreted or "patient" in interpreted
        assert "40" in interpreted or "forty" in interpreted

    def test_misheard_query_sql_targets_patients_over_40(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "shom me pashents older then fourty")
        data = resp.json()
        if not data.get("needs_clarification"):
            sql = data.get("sql", "")
            assert "patients" in sql.lower()
            assert "40" in sql or "forty" in sql.lower()

    def test_misheard_query_does_not_need_clarification(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "shom me pashents older then fourty")
        data = resp.json()
        assert data.get("needs_clarification") is False


# ---------------------------------------------------------------------------
# Regression: clean typed input
# ---------------------------------------------------------------------------

class TestCleanInputRegression:
    def test_clean_query_interpreted_text_contains_patients(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "show me patients older than 40")
        data = resp.json()
        interpreted = data.get("interpreted_text", "").lower()
        assert "patients" in interpreted

    def test_clean_query_sql_has_patients_and_40(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "show me patients older than 40")
        data = resp.json()
        sql = data.get("sql", "")
        assert "patients" in sql.lower()
        assert "40" in sql
