"""
tests/test_rag.py
-----------------
Tests for Schema-Aware Retrieval (RAG) using SentenceTransformers + FAISS.
Derived from scripts/test_rag.py.

RAG unit tests (build_schema_index, retrieve_relevant_tables) are zero-cost.
End-to-end SQL generation tests call Gemini → marked integration.
"""

import sqlite3
import tempfile
from pathlib import Path

import pytest

from app.services.rag_service import (
    build_schema_index,
    retrieve_relevant_tables,
    is_session_indexed,
    remove_schema_index,
)
from app.services.session_store import set_session, remove_session

HOSPITAL_DB = Path(__file__).resolve().parent.parent / "data" / "demo_hospital.db"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _get_hospital_schema() -> dict:
    """Return the real hospital schema dict (table_name -> list[column_names])."""
    conn = sqlite3.connect(str(HOSPITAL_DB))
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
    tables = [r[0] for r in cursor.fetchall()]
    schema = {}
    for t in tables:
        cursor.execute(f"PRAGMA table_info({t})")
        cols = [row[1] for row in cursor.fetchall()]
        schema[t] = cols
    conn.close()
    return schema


# ---------------------------------------------------------------------------
# 1. RAG index lifecycle (unit — no Gemini)
# ---------------------------------------------------------------------------

class TestRagIndexLifecycle:
    """Verify build/check/remove operations on the FAISS index."""

    def test_session_not_indexed_before_build(self):
        sid = "rag-lifecycle-test-1"
        remove_schema_index(sid)  # ensure clean state
        assert is_session_indexed(sid) is False

    def test_session_indexed_after_build(self):
        sid = "rag-lifecycle-test-2"
        schema = _get_hospital_schema()
        build_schema_index(sid, schema)
        assert is_session_indexed(sid) is True
        remove_schema_index(sid)

    def test_session_not_indexed_after_remove(self):
        sid = "rag-lifecycle-test-3"
        schema = _get_hospital_schema()
        build_schema_index(sid, schema)
        remove_schema_index(sid)
        assert is_session_indexed(sid) is False


# ---------------------------------------------------------------------------
# 2. Small-schema preservation rule (unit — no Gemini)
# ---------------------------------------------------------------------------

class TestSmallSchemaPreservation:
    """
    When a DB has <= 4 tables, RAG must return ALL tables regardless of
    similarity score (prevents accidental over-filtering of small schemas).
    """

    def test_hospital_3_tables_all_returned(self):
        sid = "rag-small-schema-test"
        schema = _get_hospital_schema()
        assert len(schema) <= 4, "Hospital demo should have <=4 tables"
        build_schema_index(sid, schema)
        retrieved = retrieve_relevant_tables(sid, "Show all patients older than 40", top_k=4)
        assert set(retrieved) == set(schema.keys()), (
            f"Small schema rule violated: expected {set(schema.keys())}, got {set(retrieved)}"
        )
        remove_schema_index(sid)

    def test_small_schema_does_not_drop_any_table(self):
        sid = "rag-small-schema-test-2"
        schema = {"users": ["id", "name", "email"], "orders": ["id", "user_id", "total"]}
        build_schema_index(sid, schema)
        retrieved = retrieve_relevant_tables(sid, "list all users", top_k=4)
        assert "users" in retrieved
        assert "orders" in retrieved
        remove_schema_index(sid)


# ---------------------------------------------------------------------------
# 3. Large-schema selective retrieval (unit — no Gemini)
# ---------------------------------------------------------------------------

class TestLargeSchemaRetrieval:
    """
    With 12 tables across 3 domains, FAISS should retrieve only the
    domain-relevant tables and not return every table.
    """

    WIDE_SCHEMA = {
        # Healthcare domain
        "patients":     ["id", "name", "age", "diagnosis"],
        "doctors":      ["id", "name", "specialty", "department"],
        "appointments": ["id", "patient_id", "doctor_id", "date"],
        "prescriptions": ["id", "patient_id", "medication", "dosage"],
        # E-commerce domain
        "customers":    ["id", "name", "email", "city"],
        "products":     ["id", "name", "category", "price"],
        "orders":       ["id", "customer_id", "product_id", "amount"],
        "reviews":      ["id", "product_id", "customer_id", "rating"],
        # Aviation domain
        "flights":      ["id", "origin", "destination", "departure_time"],
        "aircraft":     ["id", "model", "capacity", "airline_id"],
        "airports":     ["id", "code", "city", "country"],
        "airlines":     ["id", "name", "iata_code", "country"],
    }

    @pytest.fixture(autouse=True)
    def wide_schema_session(self):
        sid = "rag-wide-schema-session"
        build_schema_index(sid, self.WIDE_SCHEMA)
        self._sid = sid
        yield
        remove_schema_index(sid)

    def test_healthcare_query_retrieves_patients(self):
        tables = retrieve_relevant_tables(
            self._sid, "Show all patients diagnosed with flu", top_k=3
        )
        assert "patients" in tables

    def test_healthcare_query_does_not_retrieve_all_12_tables(self):
        tables = retrieve_relevant_tables(
            self._sid, "Show all patients diagnosed with flu", top_k=3
        )
        assert len(tables) <= 4

    def test_ecommerce_query_retrieves_orders_or_products(self):
        tables = retrieve_relevant_tables(
            self._sid, "Show the most expensive products by category", top_k=3
        )
        assert "products" in tables or "orders" in tables

    def test_aviation_query_retrieves_flights(self):
        tables = retrieve_relevant_tables(
            self._sid, "List all flights departing from New York", top_k=3
        )
        assert "flights" in tables or "airports" in tables

    def test_aviation_query_does_not_retrieve_patient_tables(self):
        tables = retrieve_relevant_tables(
            self._sid, "List all flights departing from New York", top_k=3
        )
        assert "patients" not in tables


# ---------------------------------------------------------------------------
# 4. End-to-end hospital regression (calls Gemini)
# ---------------------------------------------------------------------------

@pytest.mark.integration
class TestHospitalRagRegression:
    """Regression: after RAG index is built on connect, queries still work correctly."""

    def test_patients_query_uses_all_3_hospital_tables(self, client, hospital_sid):
        # connect-db builds the RAG index; verify it covers all 3 tables
        retrieved = retrieve_relevant_tables(
            hospital_sid, "Show all patients older than 40", top_k=4
        )
        assert "patients" in retrieved
        assert "doctors" in retrieved
        assert "appointments" in retrieved

    def test_patients_query_returns_rows(self, client, hospital_sid):
        resp = client.post("/api/query", json={
            "session_id": hospital_sid,
            "text": "Show all patients older than 40",
            "language": "en",
        })
        assert resp.status_code == 200
        assert len(resp.json()["result"]) > 0

    def test_doctors_query_returns_rows(self, client, hospital_sid):
        resp = client.post("/api/query", json={
            "session_id": hospital_sid,
            "text": "List all doctors and their specialties",
            "language": "en",
        })
        assert resp.status_code == 200
        assert len(resp.json()["result"]) > 0
