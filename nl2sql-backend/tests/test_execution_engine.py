"""
tests/test_execution_engine.py
-------------------------------
Unit tests for app.services.execution_engine.run_select().
No server, no Gemini. Uses the real hospital demo SQLite file.
Derived from test_phase3.py Case C.
"""

import sqlite3
from pathlib import Path

import pytest

from app.services.execution_engine import run_select
from app.services.session_store import set_session, SESSION_STORE

HOSPITAL_DB = Path(__file__).resolve().parent.parent / "data" / "demo_hospital.db"


@pytest.fixture()
def hospital_session(tmp_path):
    """Register a fake session pointing at the hospital demo DB and clean up after."""
    sid = "test-exec-engine-session"
    set_session(sid, {"db_path": str(HOSPITAL_DB)})
    yield sid
    SESSION_STORE.pop(sid, None)


# ---------------------------------------------------------------------------
# Happy path
# ---------------------------------------------------------------------------

class TestRunSelectHappyPath:
    def test_simple_select_returns_list(self, hospital_session):
        result = run_select(hospital_session, "SELECT * FROM patients LIMIT 5")
        assert isinstance(result, list)
        assert len(result) > 0

    def test_row_is_a_dict(self, hospital_session):
        result = run_select(hospital_session, "SELECT * FROM patients LIMIT 1")
        assert isinstance(result[0], dict)

    def test_select_count_star(self, hospital_session):
        result = run_select(hospital_session, "SELECT COUNT(*) AS total FROM patients")
        assert isinstance(result, list)
        assert "total" in result[0]
        assert result[0]["total"] > 0

    def test_select_with_where_returns_subset(self, hospital_session):
        all_rows = run_select(hospital_session, "SELECT * FROM patients")
        filtered = run_select(hospital_session, "SELECT * FROM patients WHERE age > 40")
        assert isinstance(filtered, list)
        assert len(filtered) < len(all_rows)

    def test_select_join(self, hospital_session):
        sql = (
            "SELECT p.name, d.name AS doctor FROM patients p "
            "JOIN appointments a ON p.id = a.patient_id "
            "JOIN doctors d ON d.id = a.doctor_id LIMIT 3"
        )
        result = run_select(hospital_session, sql)
        assert isinstance(result, list)
        assert "doctor" in result[0]


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

class TestRunSelectErrors:
    def test_syntax_error_returns_error_dict(self, hospital_session):
        result = run_select(hospital_session, "SELEC * FROM patients")
        assert isinstance(result, dict)
        assert "error" in result

    def test_nonexistent_table_returns_error_dict(self, hospital_session):
        result = run_select(hospital_session, "SELECT * FROM nonexistent_table")
        assert isinstance(result, dict)
        assert "error" in result

    def test_nonexistent_column_returns_error_dict(self, hospital_session):
        result = run_select(hospital_session, "SELECT no_such_col FROM patients")
        assert isinstance(result, dict)
        assert "error" in result

    def test_missing_session_returns_error_dict(self):
        result = run_select("totally-nonexistent-session-id", "SELECT 1")
        assert isinstance(result, dict)
        assert "error" in result

    def test_error_message_does_not_leak_file_path(self, hospital_session):
        result = run_select(hospital_session, "SELECT * FROM nonexistent_table")
        # The error message should not contain the full OS path to the DB file
        err = result.get("error", "")
        assert str(HOSPITAL_DB).replace("\\", "/") not in err

    def test_error_message_preserves_error_details_not_masked_by_data_word(self, hospital_session):
        # UE-01: An error referencing a table named 'data_patients' should retain the specific error, not get masked
        result = run_select(hospital_session, "SELECT * FROM data_patients")
        assert isinstance(result, dict)
        err = result.get("error", "")
        assert "no such table: data_patients" in err
