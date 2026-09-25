"""
tests/test_self_correction.py
------------------------------
Tests for the SQL self-correction retry loop.
Derived from scripts/test_self_correction.py.

Tests 1 & 3 call Gemini → marked integration.
Test 2 uses unittest.mock.patch → no Gemini call.
"""

import json
from unittest.mock import patch

import pytest

from app.models.meta_db import init_db, SessionLocal, QueryHistoryModel
from app.routers.query import _QUERY_TIMESTAMPS
from app.services.sql_generator import regenerate_sql
from app.services.sql_validator import validate_sql
from app.services.execution_engine import run_select

pytestmark = pytest.mark.integration


# ---------------------------------------------------------------------------
# Test 1: Direct unit test of regenerate_sql()
# ---------------------------------------------------------------------------

class TestRegenerateSqlUnit:
    """
    Calls Gemini's regenerate_sql() directly with a known-bad SQL + error message.
    Verifies the corrected SQL is valid and actually executes on the DB.
    """

    def test_regenerate_sql_returns_non_empty_sql(self, hospital_sid):
        result = regenerate_sql(
            session_id=hospital_sid,
            original_question="List all patient names and their ages",
            failed_sql="SELECT patient_full_name, patient_current_age FROM patients;",
            error_message="no such column: patient_full_name",
        )
        sql = result.get("sql")
        assert sql is not None and len(sql) > 0

    def test_regenerate_sql_drops_hallucinated_column(self, hospital_sid):
        result = regenerate_sql(
            session_id=hospital_sid,
            original_question="List all patient names and their ages",
            failed_sql="SELECT patient_full_name, patient_current_age FROM patients;",
            error_message="no such column: patient_full_name",
        )
        sql = result.get("sql", "")
        assert "patient_full_name" not in sql

    def test_regenerate_sql_passes_sqlglot_validation(self, hospital_sid):
        result = regenerate_sql(
            session_id=hospital_sid,
            original_question="List all patient names and their ages",
            failed_sql="SELECT patient_full_name, patient_current_age FROM patients;",
            error_message="no such column: patient_full_name",
        )
        validation = validate_sql(result.get("sql", ""))
        assert validation.get("valid") is True, f"Corrected SQL invalid: {validation}"

    def test_regenerate_sql_executes_successfully(self, hospital_sid):
        result = regenerate_sql(
            session_id=hospital_sid,
            original_question="List all patient names and their ages",
            failed_sql="SELECT patient_full_name, patient_current_age FROM patients;",
            error_message="no such column: patient_full_name",
        )
        sql = result.get("sql", "")
        exec_result = run_select(hospital_sid, sql)
        assert isinstance(exec_result, list), f"Expected list, got: {exec_result}"
        assert len(exec_result) > 0


# ---------------------------------------------------------------------------
# Test 2: End-to-end self-correction via /api/query (mock initial generate_sql)
# ---------------------------------------------------------------------------

class TestEndToEndSelfCorrection:
    """
    Patches generate_sql() to return a known-bad SQL, then verifies the
    self-correction loop catches the SQLite error, calls regenerate_sql(),
    and returns a successful response with self_corrected: True.
    No Gemini call on the *initial* generate — only on the regenerate.
    """

    _FLAWED_RESPONSE = {
        "needs_clarification": False,
        "clarification_question": None,
        "interpreted_text": "List all doctors and their medical specialty",
        "sql": "SELECT doctor_title, medical_specialty FROM doctors;",  # bad columns
        "explanation": "Retrieving doctor titles and specialties.",
        "confidence": 0.88,
    }

    def test_self_corrected_flag_is_true(self, client, hospital_sid):
        init_db()
        before = len(_QUERY_TIMESTAMPS[hospital_sid])
        with patch("app.routers.query.generate_sql", return_value=self._FLAWED_RESPONSE):
            resp = client.post("/api/query", json={
                "session_id": hospital_sid,
                "text": "List all doctors and their medical specialty",
                "language": "auto",
            })
        assert resp.status_code == 200
        assert resp.json().get("self_corrected") is True

    def test_correction_attempts_is_1(self, client, hospital_sid):
        init_db()
        with patch("app.routers.query.generate_sql", return_value=self._FLAWED_RESPONSE):
            resp = client.post("/api/query", json={
                "session_id": hospital_sid,
                "text": "List all doctors and their medical specialty",
                "language": "auto",
            })
        assert resp.json().get("correction_attempts") == 1

    def test_corrected_result_is_non_empty(self, client, hospital_sid):
        init_db()
        with patch("app.routers.query.generate_sql", return_value=self._FLAWED_RESPONSE):
            resp = client.post("/api/query", json={
                "session_id": hospital_sid,
                "text": "List all doctors and their medical specialty",
                "language": "auto",
            })
        assert len(resp.json().get("result", [])) > 0

    def test_audit_log_written_to_db(self, client, hospital_sid):
        init_db()
        with patch("app.routers.query.generate_sql", return_value=self._FLAWED_RESPONSE):
            resp = client.post("/api/query", json={
                "session_id": hospital_sid,
                "text": "List all doctors and their medical specialty",
                "language": "auto",
            })
        query_id = resp.json().get("query_id")
        db_session = SessionLocal()
        record = db_session.query(QueryHistoryModel).filter(
            QueryHistoryModel.id == int(query_id)
        ).first()
        db_session.close()
        assert record is not None
        assert record.self_corrected == 1
        assert record.correction_attempts == 1
        assert record.corrections_json is not None

    def test_corrections_json_has_expected_keys(self, client, hospital_sid):
        init_db()
        with patch("app.routers.query.generate_sql", return_value=self._FLAWED_RESPONSE):
            resp = client.post("/api/query", json={
                "session_id": hospital_sid,
                "text": "List all doctors and their medical specialty",
                "language": "auto",
            })
        query_id = resp.json().get("query_id")
        db_session = SessionLocal()
        record = db_session.query(QueryHistoryModel).filter(
            QueryHistoryModel.id == int(query_id)
        ).first()
        db_session.close()
        corrections = json.loads(record.corrections_json)
        entry = corrections[0]
        assert "attempt" in entry
        assert "failed_sql" in entry
        assert "error" in entry
        assert "corrected_sql" in entry

    def test_self_correction_counts_as_only_1_user_request(self, client, hospital_sid):
        """Retry loop must NOT consume extra rate-limit quota."""
        init_db()
        from app.routers.query import _QUERY_TIMESTAMPS
        before = len(_QUERY_TIMESTAMPS.get(hospital_sid, []))
        with patch("app.routers.query.generate_sql", return_value=self._FLAWED_RESPONSE):
            client.post("/api/query", json={
                "session_id": hospital_sid,
                "text": "List all doctors and their medical specialty",
                "language": "auto",
            })
        after = len(_QUERY_TIMESTAMPS.get(hospital_sid, []))
        assert after - before == 1, "Self-correction used more than 1 rate-limit slot"


# ---------------------------------------------------------------------------
# Test 3: Regression — normal query has self_corrected=False
# ---------------------------------------------------------------------------

class TestRegressionNormalQuery:
    def test_normal_query_self_corrected_is_false(self, client, hospital_sid):
        resp = client.post("/api/query", json={
            "session_id": hospital_sid,
            "text": "Show all patients older than 40",
            "language": "auto",
        })
        assert resp.status_code == 200
        assert resp.json().get("self_corrected") is False

    def test_normal_query_correction_attempts_is_0(self, client, hospital_sid):
        resp = client.post("/api/query", json={
            "session_id": hospital_sid,
            "text": "Show all patients older than 40",
            "language": "auto",
        })
        assert resp.json().get("correction_attempts") == 0

    def test_normal_query_returns_patient_rows(self, client, hospital_sid):
        resp = client.post("/api/query", json={
            "session_id": hospital_sid,
            "text": "Show all patients older than 40",
            "language": "auto",
        })
        assert len(resp.json().get("result", [])) > 0
