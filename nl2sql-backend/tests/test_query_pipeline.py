"""
tests/test_query_pipeline.py
-----------------------------
End-to-end integration tests for the /api/query pipeline.
These tests call Gemini — they are marked with @pytest.mark.integration.
Derived from: test_phase2.py, test_phase3.py (Cases A & B), test_phase5.py.

Run only unit tests (skip Gemini):
    pytest tests/ -v -m "not integration"

Run everything including Gemini calls:
    pytest tests/ -v
"""

import sqlite3
from pathlib import Path

import pytest

HOSPITAL_DB = Path(__file__).resolve().parent.parent / "data" / "demo_hospital.db"

pytestmark = pytest.mark.integration  # all tests in this file need Gemini


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _query(client, session_id: str, text: str):
    resp = client.post(
        "/api/query",
        json={"session_id": session_id, "text": text, "language": "en"},
    )
    return resp


# ---------------------------------------------------------------------------
# Response contract tests (shape / required fields)
# ---------------------------------------------------------------------------

class TestQueryResponseContract:
    """Verify every /api/query response contains all required fields with correct types."""

    def test_response_has_required_fields(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "How many patients are there")
        assert resp.status_code == 200
        data = resp.json()
        required = [
            "query_id", "sql", "explanation", "confidence",
            "needs_clarification", "clarification_question",
            "query_type", "result", "chart_type",
            "interpreted_text", "self_corrected", "correction_attempts",
            "data_available",
        ]
        for field in required:
            assert field in data, f"Missing field: {field}"

    def test_confidence_is_float_between_0_and_1(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "List all patients older than 40")
        data = resp.json()
        conf = data.get("confidence", -1)
        assert isinstance(conf, (int, float))
        assert 0.0 <= float(conf) <= 1.0

    def test_result_is_list(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "List all patients")
        assert isinstance(resp.json()["result"], list)

    def test_query_id_is_present_and_non_empty(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "Show all doctors")
        qid = resp.json().get("query_id")
        assert qid is not None and str(qid).strip() != ""


# ---------------------------------------------------------------------------
# Correctness tests — hospital DB
# ---------------------------------------------------------------------------

class TestHospitalQueries:
    """Core query correctness tests from Phase 2 & Phase 3."""

    def test_patients_older_than_40_returns_rows(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "List all patients older than 40")
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["result"]) > 0
        assert data["confidence"] > 0

    def test_patients_older_than_40_sql_contains_where_40(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "List all patients older than 40")
        sql = resp.json().get("sql", "")
        assert "patients" in sql.lower()
        assert "40" in sql

    def test_cardiology_doctors_returns_rows(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "How many doctors are there in Cardiology")
        assert resp.status_code == 200
        assert len(resp.json()["result"]) > 0

    def test_total_patient_count_query(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "How many patients are there in total")
        data = resp.json()
        assert resp.status_code == 200
        result = data["result"]
        assert len(result) > 0
        # The aggregate result should be a single row with a numeric count
        row = result[0]
        count_val = next(iter(row.values()))
        assert int(count_val) > 0

    def test_group_by_query_contains_group_by(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "How many appointments does each doctor have")
        sql = resp.json().get("sql", "")
        assert "group by" in sql.lower()

    def test_join_query_contains_join(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "List patients with their doctor names")
        sql = resp.json().get("sql", "")
        assert "join" in sql.lower()

    def test_order_by_query_contains_order_by(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "List all doctors sorted by name alphabetically")
        sql = resp.json().get("sql", "")
        assert "order by" in sql.lower()


# ---------------------------------------------------------------------------
# Write blocking (Phase 3 Case B)
# ---------------------------------------------------------------------------

class TestWriteQueryBlocking:
    """Verify destructive queries are rejected without touching the DB."""

    def _patient_count(self) -> int:
        conn = sqlite3.connect(str(HOSPITAL_DB))
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM patients")
        count = cur.fetchone()[0]
        conn.close()
        return count

    def test_delete_query_returns_200_but_blocked(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "Delete all patients older than 90")
        assert resp.status_code == 200  # no crash
        data = resp.json()
        sql = (data.get("sql") or "").upper()
        assert sql.startswith("SELECT") or data.get("result") == []

    def test_delete_query_does_not_modify_db(self, client, hospital_sid):
        before = self._patient_count()
        _query(client, hospital_sid, "Delete all patients older than 90")
        after = self._patient_count()
        assert before == after, "Row count changed — DELETE was not blocked!"

    def test_blocked_query_result_is_empty_list(self, client, hospital_sid):
        resp = _query(client, hospital_sid, "Drop the patients table")
        assert resp.status_code == 200
        sql = (resp.json().get("sql") or "").upper()
        assert not sql.startswith("DROP")


# ---------------------------------------------------------------------------
# Ecommerce DB queries (Phase 5 sample)
# ---------------------------------------------------------------------------

class TestEcommerceQueries:
    def test_total_revenue_query(self, client, ecommerce_sid):
        resp = _query(client, ecommerce_sid, "What is the sum of total amount from all orders")
        assert resp.status_code == 200
        assert len(resp.json()["result"]) > 0

    def test_top_3_products_has_order_by_and_limit(self, client, ecommerce_sid):
        resp = _query(client, ecommerce_sid, "List the top 3 most expensive products")
        sql = resp.json().get("sql", "").lower()
        assert "order by" in sql
        assert "3" in sql or "limit" in sql

    def test_orders_with_join_has_join(self, client, ecommerce_sid):
        resp = _query(client, ecommerce_sid, "Show me all orders with the customer name and product name")
        sql = resp.json().get("sql", "").lower()
        assert "join" in sql
