"""
tests/test_clarification.py
----------------------------
Tests for the question clarification layer (needs_clarification field).
Derived from scripts/test_clarification.py.

These call Gemini → marked integration.
"""

import pytest

pytestmark = pytest.mark.integration


def _query(client, session_id, text):
    return client.post("/api/query", json={"session_id": session_id, "text": text})


# ---------------------------------------------------------------------------
# Ambiguous queries → should request clarification
# ---------------------------------------------------------------------------

class TestClarificationRequired:
    def test_vague_top_patients_needs_clarification(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "give me the top patients")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("needs_clarification") is True

    def test_clarification_question_is_non_empty_for_vague_query(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "give me the top patients")
        data = resp.json()
        assert data.get("clarification_question") is not None
        assert len(data.get("clarification_question", "")) > 5

    def test_sql_is_null_when_clarification_needed(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "show me important doctors")
        data = resp.json()
        if data.get("needs_clarification"):
            assert data.get("sql") is None

    def test_result_is_empty_when_clarification_needed(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "give me the top patients")
        data = resp.json()
        if data.get("needs_clarification"):
            assert data.get("result", []) == []

    def test_confidence_low_when_clarification_needed(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "give me the top patients")
        data = resp.json()
        if data.get("needs_clarification"):
            assert data.get("confidence", 1.0) < 0.5


# ---------------------------------------------------------------------------
# Specific queries → should NOT need clarification
# ---------------------------------------------------------------------------

class TestClarificationNotRequired:
    def test_specific_ranked_query_no_clarification(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "top 5 patients by number of appointments")
        assert resp.status_code == 200
        data = resp.json()
        assert data.get("needs_clarification") is False

    def test_specific_ranked_query_sql_contains_limit(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "top 5 patients by number of appointments")
        sql = resp.json().get("sql", "")
        assert "5" in sql or "limit" in sql.lower()

    def test_regression_patients_older_than_40_no_clarification(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "list all patients older than 40")
        assert resp.json().get("needs_clarification") is False

    def test_regression_patients_older_than_40_sql_has_where_40(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "list all patients older than 40")
        sql = resp.json().get("sql", "")
        assert "where" in sql.lower()
        assert "40" in sql
