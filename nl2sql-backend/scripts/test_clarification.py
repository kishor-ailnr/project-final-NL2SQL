"""Test script for question clarification layer in NL2SQL assistant.

Covers 4 test cases against the hospital demo database:
1. "give me the top patients" -> needs_clarification: true
2. "top 5 patients by number of appointments" -> needs_clarification: false, valid SQL with LIMIT 5
3. "show me important doctors" -> needs_clarification: true
4. "list all patients older than 40" -> needs_clarification: false, regression check working as before
"""

import sys
from pathlib import Path
from starlette.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app
from app.routers.query import reset_rate_limits
from app.services.sql_generator import clear_query_cache

client = TestClient(app)


def run_tests():
    print("=" * 75)
    print("           NL2SQL CLARIFICATION LAYER TEST SUITE")
    print("=" * 75)

    reset_rate_limits()
    clear_query_cache()

    # Step 0: Connect to demo hospital database
    conn_resp = client.post("/api/connect-db", json={"db_type": "demo", "demo_name": "hospital"})
    assert conn_resp.status_code == 200, f"Failed to connect: {conn_resp.text}"
    session_id = conn_resp.json()["session_id"]
    print(f"Connected to demo hospital DB. Session ID: {session_id}\n")

    test_cases = [
        {
            "id": 1,
            "query": "give me the top patients",
            "expected_clarification": True,
            "description": "Ambiguous ranking without metric and limit",
        },
        {
            "id": 2,
            "query": "top 5 patients by number of appointments",
            "expected_clarification": False,
            "must_contain_sql": ["LIMIT", "5"],
            "description": "Specific ranking with metric and limit",
        },
        {
            "id": 3,
            "query": "show me important doctors",
            "expected_clarification": True,
            "description": "Vague qualitative term ('important') without criteria",
        },
        {
            "id": 4,
            "query": "list all patients older than 40",
            "expected_clarification": False,
            "must_contain_sql": ["WHERE", "40"],
            "description": "Regression check - unambiguous filter on patients",
        },
    ]

    all_passed = True

    for tc in test_cases:
        print("-" * 75)
        print(f"TEST CASE {tc['id']}: \"{tc['query']}\"")
        print(f"Description: {tc['description']}")
        print("-" * 75)

        # Clear query cache to test fresh generation
        clear_query_cache(session_id)

        resp = client.post(
            "/api/query",
            json={"session_id": session_id, "text": tc["query"]},
        )

        if resp.status_code != 200:
            print(f"[FAIL] HTTP Status: {resp.status_code}, Response: {resp.text}")
            all_passed = False
            continue

        data = resp.json()
        needs_clarif = data.get("needs_clarification")
        clarif_q = data.get("clarification_question")
        sql = data.get("sql")
        explanation = data.get("explanation")
        confidence = data.get("confidence")
        result = data.get("result", [])

        print(f"needs_clarification    : {needs_clarif}")
        print(f"clarification_question : {clarif_q}")
        print(f"generated_sql          : {sql}")
        print(f"confidence             : {confidence}")
        print(f"rows_returned          : {len(result)}")

        # Verification
        tc_passed = True
        if needs_clarif != tc["expected_clarification"]:
            print(f"[FAIL] Expected needs_clarification={tc['expected_clarification']}, got {needs_clarif}")
            tc_passed = False

        if tc["expected_clarification"]:
            if not clarif_q:
                print("[FAIL] Expected non-empty clarification_question")
                tc_passed = False
            if sql is not None:
                print(f"[FAIL] Expected sql to be null, got: {sql}")
                tc_passed = False
            if len(result) != 0:
                print(f"[FAIL] Expected result to be empty, got {len(result)} rows")
                tc_passed = False
            if confidence >= 0.5:
                print(f"[FAIL] Expected confidence < 0.5, got {confidence}")
                tc_passed = False
        else:
            if sql is None or not sql.strip():
                print("[FAIL] Expected valid SQL string, got null or empty")
                tc_passed = False
            if clarif_q is not None:
                print(f"[FAIL] Expected clarification_question to be null, got: {clarif_q}")
                tc_passed = False
            for token in tc.get("must_contain_sql", []):
                if token.lower() not in (sql or "").lower():
                    print(f"[FAIL] SQL expected to contain '{token}', got: {sql}")
                    tc_passed = False

        if tc_passed:
            print(f"-> CASE {tc['id']} RESULT: [PASS]")
        else:
            print(f"-> CASE {tc['id']} RESULT: [FAIL]")
            all_passed = False
        print()

    print("=" * 75)
    if all_passed:
        print(">>> ALL 4 CLARIFICATION TEST CASES PASSED SUCCESSFULLY! <<<")
    else:
        print(">>> SOME CLARIFICATION TEST CASES FAILED <<<")
    print("=" * 75)
    return all_passed


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
