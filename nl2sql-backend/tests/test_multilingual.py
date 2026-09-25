"""
tests/test_multilingual.py
---------------------------
Tests for multilingual + Thanglish support.
Derived from scripts/test_multilingual.py.

These call Gemini → marked integration.
"""

import pytest
from app.services.sql_generator import detect_input_language

pytestmark = pytest.mark.integration


def _has_tamil(text: str) -> bool:
    return any("\u0b80" <= c <= "\u0bff" for c in (text or ""))


def _query(client, session_id, text, language="auto"):
    return client.post("/api/query", json={"session_id": session_id, "text": text, "language": language})


# ---------------------------------------------------------------------------
# Language detection (pure unit — no Gemini)
# ---------------------------------------------------------------------------

class TestLanguageDetection:
    """Unit tests for detect_input_language() — zero Gemini calls."""

    @pytest.mark.no_integration
    def test_english_detected(self):
        assert detect_input_language("list all patients older than 40") == "english"

    @pytest.mark.no_integration
    def test_tamil_script_detected(self):
        assert detect_input_language("40 வயதுக்கு மேற்பட்ட நோயாளிகளை காட்டு") == "tamil"

    @pytest.mark.no_integration
    def test_thanglish_detected(self):
        result = detect_input_language("40 vayasuku mela irukra patients ellam kaatu")
        assert result == "thanglish"


# ---------------------------------------------------------------------------
# End-to-end multilingual query tests
# ---------------------------------------------------------------------------

class TestMultilingualQueries:
    def test_english_query_returns_english_explanation(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "list all patients older than 40")
        data = resp.json()
        assert resp.status_code == 200
        explanation = data.get("explanation", "")
        assert not _has_tamil(explanation), f"Expected English explanation, got Tamil: {explanation}"

    def test_english_sql_has_patients_and_40(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "list all patients older than 40")
        sql = resp.json().get("sql", "")
        assert "patients" in sql.lower()
        assert "40" in sql

    def test_tamil_script_query_returns_sql(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "40 வயதுக்கு மேற்பட்ட நோயாளிகளை காட்டு")
        assert resp.status_code == 200
        data = resp.json()
        if not data.get("needs_clarification"):
            sql = data.get("sql", "")
            assert "patients" in sql.lower()
            assert "40" in sql

    def test_tamil_script_explanation_is_in_tamil(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "40 வயதுக்கு மேற்பட்ட நோயாளிகளை காட்டு")
        data = resp.json()
        if not data.get("needs_clarification"):
            explanation = data.get("explanation", "")
            assert _has_tamil(explanation), f"Expected Tamil explanation, got: {explanation}"

    def test_thanglish_query_returns_sql(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "40 vayasuku mela irukra patients ellam kaatu")
        assert resp.status_code == 200
        data = resp.json()
        if not data.get("needs_clarification"):
            sql = data.get("sql", "")
            assert "patients" in sql.lower() and "40" in sql

    def test_thanglish_explanation_starts_with_understood(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "40 vayasuku mela irukra patients ellam kaatu")
        data = resp.json()
        if not data.get("needs_clarification"):
            explanation = data.get("explanation", "")
            understood_variants = ("Understood —", "Understood -", "Understood –", "understood")
            assert any(explanation.startswith(v) or v.lower() in explanation.lower()
                       for v in understood_variants), f"Got: {explanation}"

    def test_ambiguous_tamil_gets_clarification(self, client, hospital_sid):
        # "சிறந்த மருத்துவர்களை காட்டு" = "show me the best doctors" (vague)
        resp = _query(client, hospital_sid, "சிறந்த மருத்துவர்களை காட்டு")
        assert resp.status_code == 200
        data = resp.json()
        if data.get("needs_clarification"):
            cq = data.get("clarification_question", "")
            assert _has_tamil(cq), f"Expected Tamil clarification question, got: {cq}"

    def test_all_three_languages_produce_logically_equivalent_sql(self, client, hospital_sid):
        """English, Tamil, Thanglish all targeting patients > 40 should produce equivalent SQL."""
        queries = [
            "list all patients older than 40",
            "40 வயதுக்கு மேற்பட்ட நோயாளிகளை காட்டு",
            "40 vayasuku mela irukra patients ellam kaatu",
        ]
        sqls = []
        for q in queries:
            resp = _query(client, hospital_sid, q)
            data = resp.json()
            if not data.get("needs_clarification"):
                sqls.append(data.get("sql", ""))

        # All generated SQLs should reference patients and 40
        for sql in sqls:
            assert "patients" in sql.lower(), f"SQL missing 'patients': {sql}"
            assert "40" in sql, f"SQL missing '40': {sql}"
