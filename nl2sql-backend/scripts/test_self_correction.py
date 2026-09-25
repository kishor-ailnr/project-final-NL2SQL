"""Test suite for Self-Correction Retry Loop in NL2SQL assistant.

Validates:
1. Direct test of regenerate_sql() with erroneous SQL & SQLite error message.
2. End-to-end /api/query self-correction test:
   - Deliberately injects a bad SQL (wrong column name) on initial generation.
   - Verifies the self-correction loop catches the error, calls Gemini regenerate_sql().
   - Confirms corrected SQL is valid, executes on the database, and returns results.
   - Confirms 'self_corrected: True' and 'correction_attempts: 1' are returned in QueryResponse.
   - Confirms query_history in meta.db records the correction audit log.
3. Regression test:
   - Normal query generates correct SQL on first attempt.
   - Confirms 'self_corrected: False' and 'correction_attempts: 0'.
4. Rate limiting verification:
   - Confirms a query with self-correction retries counts as ONLY 1 user request against the 20/min limit.
"""

import sys
import json
from pathlib import Path
from unittest.mock import patch

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from starlette.testclient import TestClient
from app.main import app
from app.models.meta_db import init_db, SessionLocal, QueryHistoryModel
from app.routers.query import reset_rate_limits, _QUERY_TIMESTAMPS
from app.services.sql_generator import regenerate_sql, clear_query_cache
from app.services.sql_validator import validate_sql
from app.services.execution_engine import run_select

client = TestClient(app)


def test_self_correction_suite():
    print("=" * 80)
    print("        NL2SQL SELF-CORRECTION RETRY LOOP VERIFICATION SUITE")
    print("=" * 80)

    # Initialize DB migrations (ensure self_corrected and corrections_json columns exist)
    init_db()
    reset_rate_limits()
    clear_query_cache()

    # Step 0: Connect to demo hospital database
    conn_resp = client.post("/api/connect-db", json={"db_type": "demo", "demo_name": "hospital"})
    assert conn_resp.status_code == 200, f"Connect failed: {conn_resp.text}"
    session_id = conn_resp.json()["session_id"]
    print(f"\n[Setup] Connected to demo hospital DB. Session ID: {session_id}")

    # --------------------------------------------------------------------------
    # TEST 1: Direct Unit Test of regenerate_sql()
    # --------------------------------------------------------------------------
    print("\n" + "-" * 75)
    print("TEST 1: Direct Unit Test of regenerate_sql() with Execution Failure")
    print("-" * 75)

    original_q = "List all patient names and their ages"
    bad_sql = "SELECT patient_full_name, patient_current_age FROM patients;"
    simulated_error = "no such column: patient_full_name"

    print(f"  Original Question : \"{original_q}\"")
    print(f"  Erroneous SQL     : {bad_sql}")
    print(f"  Error Message     : {simulated_error}")

    regen_result = regenerate_sql(
        session_id=session_id,
        original_question=original_q,
        failed_sql=bad_sql,
        error_message=simulated_error,
    )

    corrected_sql = regen_result.get("sql")
    corrected_exp = regen_result.get("explanation")
    print(f"\n  Gemini Corrected SQL : {corrected_sql}")
    print(f"  Gemini Explanation   : {corrected_exp}")

    assert corrected_sql is not None and len(corrected_sql) > 0, "Regenerated SQL must not be empty"
    assert "patient_full_name" not in corrected_sql, "Corrected SQL must not retain the hallucinated column"

    # Validate syntax via sqlglot
    validation = validate_sql(corrected_sql)
    assert validation.get("valid", False), f"Corrected SQL failed syntax validation: {validation}"
    print("   Corrected SQL passed sqlglot syntax validation.")

    # Execute against SQLite database
    exec_res = run_select(session_id, corrected_sql)
    assert not (isinstance(exec_res, dict) and "error" in exec_res), f"Execution failed: {exec_res}"
    assert isinstance(exec_res, list) and len(exec_res) > 0, "Corrected SQL returned empty rows"
    print(f"   Corrected SQL executed successfully. Rows returned: {len(exec_res)}")
    print(f"   Sample row: {exec_res[0]}")
    print(" TEST 1 PASSED: regenerate_sql() successfully diagnosed and fixed the error!")

    # --------------------------------------------------------------------------
    # TEST 2: End-to-End Self-Correction via /api/query Endpoint
    # --------------------------------------------------------------------------
    print("\n" + "-" * 75)
    print("TEST 2: End-to-End /api/query Self-Correction Retry Loop")
    print("-" * 75)

    # We patch generate_sql once to simulate Gemini generating an erroneous SQL on attempt 0
    flawed_initial_response = {
        "needs_clarification": False,
        "clarification_question": None,
        "interpreted_text": "List all doctors and their medical specialty",
        "sql": "SELECT doctor_title, medical_specialty FROM doctors;",  # Invalid column names
        "explanation": "Retrieving doctor titles and specialties.",
        "confidence": 0.88,
    }

    initial_timestamps_count = len(_QUERY_TIMESTAMPS[session_id])

    with patch("app.routers.query.generate_sql", return_value=flawed_initial_response):
        q_resp = client.post(
            "/api/query",
            json={
                "session_id": session_id,
                "text": "List all doctors and their medical specialty",
                "language": "auto",
            },
        )

    assert q_resp.status_code == 200, f"Query endpoint failed: {q_resp.text}"
    resp_data = q_resp.json()

    print(f"  Response received:")
    print(f"   Final SQL            : {resp_data.get('sql')}")
    print(f"   self_corrected       : {resp_data.get('self_corrected')}")
    print(f"   correction_attempts  : {resp_data.get('correction_attempts')}")
    print(f"   Rows returned        : {len(resp_data.get('result', []))}")

    # Assertions for Self-Correction
    assert resp_data.get("self_corrected") is True, "Expected self_corrected: true in response"
    assert resp_data.get("correction_attempts") == 1, f"Expected 1 correction attempt, got {resp_data.get('correction_attempts')}"
    assert len(resp_data.get("result", [])) > 0, "Expected non-empty result rows after successful self-correction"

    # Verify Database Audit Log & Corrections JSON in query_history table
    db_session = SessionLocal()
    record = (
        db_session.query(QueryHistoryModel)
        .filter(QueryHistoryModel.id == int(resp_data["query_id"]))
        .first()
    )
    assert record is not None, "Query record not found in meta.db"
    assert record.self_corrected == 1, f"Expected record.self_corrected=1, got {record.self_corrected}"
    assert record.correction_attempts == 1, f"Expected record.correction_attempts=1, got {record.correction_attempts}"
    assert record.corrections_json is not None, "Expected corrections_json in database record"

    corrections = json.loads(record.corrections_json)
    print(f"\n  Stored Audit Trail in meta.db (query_history id={record.id}):")
    print(f"   Attempt Number : {corrections[0]['attempt']}")
    print(f"   Failed SQL     : {corrections[0]['failed_sql']}")
    print(f"   Caught Error   : {corrections[0]['error']}")
    print(f"   Fixed SQL      : {corrections[0]['corrected_sql']}")
    db_session.close()

    # Rate Limiting Check: verify that the retry loop did NOT increment user rate limit count
    final_timestamps_count = len(_QUERY_TIMESTAMPS[session_id])
    request_delta = final_timestamps_count - initial_timestamps_count
    print(f"\n  Rate Limit Verification:")
    print(f"   User requests recorded in sliding window: {request_delta}")
    assert request_delta == 1, f"Rate limit recorded {request_delta} requests instead of exactly 1!"
    print("   Confirmed: self-correction retries do NOT consume user rate limit quota.")

    print(" TEST 2 PASSED: End-to-end self-correction retry loop and audit log verified!")

    # --------------------------------------------------------------------------
    # TEST 3: Regression Test - Normal Query Works on First Try
    # --------------------------------------------------------------------------
    print("\n" + "-" * 75)
    print("TEST 3: Regression Test - Clean First-Try Query (self_corrected=False)")
    print("-" * 75)

    clean_resp = client.post(
        "/api/query",
        json={
            "session_id": session_id,
            "text": "Show all patients older than 40",
            "language": "auto",
        },
    )
    assert clean_resp.status_code == 200, f"Query failed: {clean_resp.text}"
    clean_data = clean_resp.json()

    print(f"  SQL Generated       : {clean_data.get('sql')}")
    print(f"  self_corrected      : {clean_data.get('self_corrected')}")
    print(f"  correction_attempts : {clean_data.get('correction_attempts')}")
    print(f"  Rows returned       : {len(clean_data.get('result', []))}")

    assert clean_data.get("self_corrected") is False, "Normal query must have self_corrected: false"
    assert clean_data.get("correction_attempts") == 0, "Normal query must have correction_attempts: 0"
    assert len(clean_data.get("result", [])) > 0, "Expected patient rows returned"

    print(" TEST 3 PASSED: Zero overhead or regression on normal clean queries.")

    print("\n" + "=" * 80)
    print(" ALL SELF-CORRECTION TESTS PASSED SUCCESSFULLY! ")
    print("=" * 80)


if __name__ == "__main__":
    test_self_correction_suite()
