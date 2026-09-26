"""
tests/test_adapters_and_writes.py
---------------------------------
Automated tests for:
1. Database Adapter Architecture (SQLiteAdapter, PostgreSQLAdapter, DatabaseConnectionManager)
2. Complete Schema Extraction (tables, columns, types, PKs, FKs, relationships, row counts, sample values)
3. Controlled Read/Write Execution Engine with Transaction Handling
4. Staged Write Query Confirmation Loop (POST /api/confirm-write)
5. Direct Database Connection Strings via POST /api/connect-db
"""

import sqlite3
import pytest
from pathlib import Path
from starlette.testclient import TestClient

from app.database.sqlite_adapter import SQLiteAdapter
from app.database.postgres_adapter import PostgreSQLAdapter
from app.database.manager import DatabaseConnectionManager
from app.services.execution_engine import run_select, run_write
from app.routers.query import _PENDING_WRITES


# ---------------------------------------------------------------------------
# Module 1 & 2: Database Adapters and Schema Extraction
# ---------------------------------------------------------------------------

class TestDatabaseAdapters:
    def test_sqlite_adapter_connect_and_schema(self, tmp_path):
        db_file = tmp_path / "test_clinic.db"
        conn = sqlite3.connect(str(db_file))
        cursor = conn.cursor()
        cursor.execute("CREATE TABLE departments (dept_id INTEGER PRIMARY KEY, name TEXT NOT NULL);")
        cursor.execute("CREATE TABLE staff (staff_id INTEGER PRIMARY KEY, name TEXT, dept_id INTEGER, FOREIGN KEY(dept_id) REFERENCES departments(dept_id));")
        cursor.execute("INSERT INTO departments VALUES (1, 'Cardiology'), (2, 'Neurology');")
        cursor.execute("INSERT INTO staff VALUES (101, 'Dr. Smith', 1), (102, 'Dr. Patel', 2);")
        conn.commit()
        conn.close()

        adapter = SQLiteAdapter(db_path=db_file)
        val = adapter.validate_connection()
        assert val is True

        schema_data = adapter.extract_full_schema()
        assert "departments" in schema_data["tables"]
        assert "staff" in schema_data["tables"]

        dept_cols = {c["name"]: c for c in schema_data["schema"]["departments"]}
        assert dept_cols["dept_id"]["primary_key"] is True
        assert dept_cols["name"]["nullable"] is False

        # Verify foreign keys & relationships
        rel = schema_data["relationships"]
        assert len(rel) == 1
        assert rel[0]["from_table"] == "staff"
        assert rel[0]["from_column"] == "dept_id"
        assert rel[0]["to_table"] == "departments"
        assert rel[0]["to_column"] == "dept_id"

        # Verify sample values
        samples = adapter.get_sample_values("departments", "name")
        assert "Cardiology" in samples

        # Verify select execution
        rows = adapter.execute_query("SELECT name FROM departments ORDER BY dept_id")
        assert len(rows) == 2
        assert rows[0]["name"] == "Cardiology"

        # Verify write execution
        w_res = adapter.execute_write("UPDATE departments SET name = 'Heart Center' WHERE dept_id = 1")
        assert w_res["success"] is True
        assert w_res["rows_affected"] == 1

        # Verify multi-statement SELECT
        multi_rows = adapter.execute_query("SELECT name FROM departments WHERE dept_id = 1; SELECT name FROM staff WHERE staff_id = 101;")
        assert len(multi_rows) == 2

        # Verify multi-statement WRITE
        multi_w = adapter.execute_write("UPDATE departments SET name = 'Neuro' WHERE dept_id = 2; INSERT INTO departments VALUES (3, 'Pediatrics');")
        assert multi_w["success"] is True
        assert multi_w["rows_affected"] == 2

        adapter.disconnect()

    def test_postgres_adapter_safe_validation(self):
        adapter = PostgreSQLAdapter(connection_string="postgresql://invalid:invalid@127.0.0.1:5432/nonexistent")
        res = adapter.validate_connection()
        # Must return boolean False safely without crashing or raising unhandled exception
        assert res is False

    def test_connection_manager_registration(self, tmp_path):
        db_file = tmp_path / "mgr_test.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE items (id INT, val TEXT);")
        conn.commit()
        conn.close()

        session_id = "test-mgr-sid-123"
        adapter = SQLiteAdapter(db_path=db_file)
        DatabaseConnectionManager.register_adapter(session_id, adapter)

        retrieved = DatabaseConnectionManager.get_adapter(session_id)
        assert retrieved is adapter

        DatabaseConnectionManager.remove_adapter(session_id)
        assert DatabaseConnectionManager.get_adapter(session_id) is None


# ---------------------------------------------------------------------------
# Module 10: Controlled Write Confirmation Workflow
# ---------------------------------------------------------------------------

class TestWriteConfirmationWorkflow:
    def test_confirm_write_cancelled(self, client: TestClient, hospital_sid: str):
        # Stage a pending write manually in _PENDING_WRITES
        qid = "test-write-cancel-999"
        _PENDING_WRITES[qid] = {
            "session_id": hospital_sid,
            "conversation_id": "conv-test-1",
            "sql": "UPDATE patients SET age = 99 WHERE id = 1",
            "explanation": "Update patient age to 99",
        }

        resp = client.post("/api/confirm-write", json={
            "session_id": hospital_sid,
            "query_id": qid,
            "confirmed": False,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "cancelled"
        assert data["rows_affected"] == 0
        assert qid not in _PENDING_WRITES

    def test_confirm_write_executed(self, client: TestClient, hospital_sid: str):
        # First check initial age of patient 1
        sel_resp = run_select(hospital_sid, "SELECT age FROM patients WHERE id = 1")
        assert isinstance(sel_resp, list) and len(sel_resp) > 0
        original_age = sel_resp[0]["age"]
        new_age = original_age + 1

        qid = "test-write-exec-888"
        _PENDING_WRITES[qid] = {
            "session_id": hospital_sid,
            "conversation_id": "conv-test-2",
            "sql": f"UPDATE patients SET age = {new_age} WHERE id = 1",
            "explanation": f"Update patient age to {new_age}",
        }

        resp = client.post("/api/confirm-write", json={
            "session_id": hospital_sid,
            "query_id": qid,
            "confirmed": True,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "executed"
        assert data["rows_affected"] == 1

        # Verify update actually modified the database
        verify_resp = run_select(hospital_sid, "SELECT age FROM patients WHERE id = 1")
        assert verify_resp[0]["age"] == new_age

    def test_full_write_operation_flow(self, client: TestClient, hospital_sid: str):
        """
        3. A full write-operation flow test: submit a write query, confirm it,
        and verify the actual database row is modified afterward (query the table directly
        to prove the UPDATE/DELETE actually ran).
        """
        # Read current age of Pavai
        pre_check = run_select(hospital_sid, "SELECT name, age FROM patients WHERE name LIKE '%Pavai%'")
        assert len(pre_check) > 0, "Patient Pavai not found in test database"
        pavai_name = pre_check[0]["name"]

        # Submit write query through /api/query
        submit_resp = client.post("/api/query", json={
            "session_id": hospital_sid,
            "text": "update the age of patient Pavai to 35",
            "language": "auto",
        })
        assert submit_resp.status_code == 200
        submit_data = submit_resp.json()
        assert submit_data.get("query_type") == "write"
        query_id = submit_data.get("query_id")
        assert query_id is not None
        assert query_id in _PENDING_WRITES

        # Confirm write query through /api/confirm-write
        confirm_resp = client.post("/api/confirm-write", json={
            "session_id": hospital_sid,
            "query_id": query_id,
            "confirmed": True,
        })
        assert confirm_resp.status_code == 200
        confirm_data = confirm_resp.json()
        assert confirm_data.get("status") == "executed"
        assert confirm_data.get("rows_affected") >= 1

        # Query the table directly to prove the database row was actually modified
        post_check = run_select(hospital_sid, f"SELECT name, age FROM patients WHERE name = '{pavai_name}'")
        assert len(post_check) > 0
        assert post_check[0]["age"] == 35, f"Expected age 35, but got {post_check[0]['age']}"

    def test_confirm_write_not_found(self, client: TestClient, hospital_sid: str):
        resp = client.post("/api/confirm-write", json={
            "session_id": hospital_sid,
            "query_id": "non-existent-query-id",
            "confirmed": True,
        })
        assert resp.status_code == 404


# ---------------------------------------------------------------------------
# Module 1: Direct Connection String Endpoint Integration
# ---------------------------------------------------------------------------

class TestDirectConnectDB:
    def test_connect_sqlite_file_path(self, client: TestClient, tmp_path):
        db_file = tmp_path / "custom_clinic.db"
        conn = sqlite3.connect(str(db_file))
        conn.execute("CREATE TABLE rooms (room_no INT PRIMARY KEY, capacity INT);")
        conn.execute("INSERT INTO rooms VALUES (101, 2), (102, 4);")
        conn.commit()
        conn.close()

        resp = client.post("/api/connect-db", json={
            "db_type": "sqlite",
            "connection_string": f"sqlite:///{db_file.as_posix()}",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "connected"
        assert "rooms" in data["tables"]
        sid = data["session_id"]

        # Run query through the created session
        q_resp = run_select(sid, "SELECT COUNT(*) as count FROM rooms")
        assert q_resp[0]["count"] == 2


# ---------------------------------------------------------------------------
# Write Operation Security & Safety Verifications
# ---------------------------------------------------------------------------

class TestWriteSecurityAndSafety:
    def test_cross_session_write_confirmation_rejected(self, client: TestClient, hospital_sid: str, ecommerce_sid: str):
        """1. Re-validates query_id belongs to the CURRENT session_id. Cross-session write is 403."""
        qid = "cross-sess-test-qid-1"
        _PENDING_WRITES[qid] = {
            "session_id": hospital_sid,
            "conversation_id": "conv-hospital-1",
            "sql": "UPDATE patients SET age = 99 WHERE id = 1",
            "explanation": "Update age to 99",
        }

        # Attempt to confirm using a different session (ecommerce_sid)
        resp = client.post("/api/confirm-write", json={
            "session_id": ecommerce_sid,
            "query_id": qid,
            "confirmed": True,
        })
        assert resp.status_code == 403, f"Expected 403 Forbidden, got {resp.status_code}: {resp.text}"
        assert "different session" in resp.json().get("detail", "").lower()

        # Verify SQL was NOT executed in hospital DB
        res = run_select(hospital_sid, "SELECT age FROM patients WHERE id = 1")
        assert res[0]["age"] != 99

        # Clean up
        _PENDING_WRITES.pop(qid, None)

    def test_invented_query_id_cannot_execute(self, client: TestClient, hospital_sid: str):
        """2. Calling /api/confirm-write with an invented query_id returns 404."""
        resp = client.post("/api/confirm-write", json={
            "session_id": hospital_sid,
            "query_id": "invented-fake-id-9999",
            "confirmed": True,
        })
        assert resp.status_code == 404, f"Expected 404 Not Found, got {resp.status_code}: {resp.text}"
        assert "not found" in resp.json().get("detail", "").lower()

    def test_double_confirmation_replay_prevented(self, client: TestClient, hospital_sid: str):
        """3. Calling confirm-write twice on the same query_id cannot execute write twice."""
        # Initial age
        init_rows = run_select(hospital_sid, "SELECT age FROM patients WHERE id = 2")
        init_age = init_rows[0]["age"]

        qid = "replay-test-qid-333"
        _PENDING_WRITES[qid] = {
            "session_id": hospital_sid,
            "conversation_id": "conv-replay-test",
            "sql": f"UPDATE patients SET age = age + 1 WHERE id = 2",
            "explanation": "Increment age by 1",
        }

        # First call -> Executed once
        resp1 = client.post("/api/confirm-write", json={
            "session_id": hospital_sid,
            "query_id": qid,
            "confirmed": True,
        })
        assert resp1.status_code == 200
        assert resp1.json()["status"] == "executed"
        assert resp1.json()["rows_affected"] == 1

        # Direct DB check after first execution
        mid_rows = run_select(hospital_sid, "SELECT age FROM patients WHERE id = 2")
        assert mid_rows[0]["age"] == init_age + 1

        # Second call (replay / double-click)
        resp2 = client.post("/api/confirm-write", json={
            "session_id": hospital_sid,
            "query_id": qid,
            "confirmed": True,
        })
        # Must be rejected (404 because popped, or already executed notice) and NOT run again
        if resp2.status_code == 200:
            assert resp2.json().get("rows_affected", 0) == 0, "Second call must not affect rows"
        else:
            assert resp2.status_code in (404, 409), f"Expected 404/409, got {resp2.status_code}"

        # Direct DB check after second call: age must STILL be init_age + 1, not incremented again!
        final_rows = run_select(hospital_sid, "SELECT age FROM patients WHERE id = 2")
        assert final_rows[0]["age"] == init_age + 1, f"Age was incremented twice! Expected {init_age + 1}, got {final_rows[0]['age']}"

    def test_rate_limiting_enforced_on_confirm_write(self, client: TestClient, hospital_sid: str):
        """4. Confirm rate limiting applies to /api/confirm-write (max 20 req/min per session)."""
        from app.routers.query import reset_rate_limits
        reset_rate_limits()

        # Fire 20 requests (each can 404 or succeed, but rate limit bucket counts them)
        for i in range(20):
            r = client.post("/api/confirm-write", json={
                "session_id": hospital_sid,
                "query_id": f"dummy-rate-test-{i}",
                "confirmed": False,
            })
            assert r.status_code in (200, 404), f"Unexpected status on request {i}: {r.status_code}"

        # The 21st request MUST be rejected with HTTP 429
        r21 = client.post("/api/confirm-write", json={
            "session_id": hospital_sid,
            "query_id": "dummy-rate-test-21",
            "confirmed": False,
        })
        assert r21.status_code == 429, f"Expected 429 Too Many Requests, got {r21.status_code}: {r21.text}"
        assert "Retry-After" in r21.headers

