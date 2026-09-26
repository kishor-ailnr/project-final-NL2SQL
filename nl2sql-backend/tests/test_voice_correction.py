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


# ---------------------------------------------------------------------------
# Data values vs Schema typos (Bug 3)
# ---------------------------------------------------------------------------

class TestTypoCorrectionVsDataValues:
    def test_proper_noun_data_value_not_flagged_as_typo(self, client, hospital_sid):
        """
        1. 'delete the age of patient Pavai' — corrected_terms must be empty
        (Pavai should NOT be flagged), and the SQL should correctly reference
        the literal value 'Pavai' in a WHERE clause.
        """
        resp = _query(client, hospital_sid, "delete the age of patient Pavai")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("corrected_terms") == [], f"Expected empty corrected_terms, got: {data.get('corrected_terms')}"
        sql = data.get("sql", "")
        assert "Pavai" in sql or "pavai" in sql.lower(), f"Expected 'Pavai' literal in SQL, got: {sql}"
        assert "WHERE" in sql.upper(), f"Expected WHERE clause in SQL, got: {sql}"

    def test_schema_term_typo_is_flagged(self, client, hospital_sid):
        """
        2. 'show me paiens older than 40' — corrected_terms SHOULD still flag
        'paiens' -> 'patients' (regression check, this is a genuine schema typo).
        """
        resp = _query(client, hospital_sid, "show me paiens older than 40")
        assert resp.status_code == 200
        data = resp.json()
        corrected = data.get("corrected_terms", [])
        assert any(
            item.get("original", "").lower() == "paiens" and "patient" in item.get("corrected", "").lower()
            for item in corrected
        ), f"Expected 'paiens' -> 'patients' correction, got: {corrected}"

