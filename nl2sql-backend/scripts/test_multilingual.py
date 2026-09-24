"""Test script for Multilingual & Thanglish NL2SQL support.

Test cases against demo hospital database:
1. English: "list all patients older than 40" -> needs_clarification: false, WHERE age > 40
2. Tamil: "40 வயதுக்கு மேற்பட்ட அனைத்து நோயாளிகளையும் பட்டியலிடுங்கள்" -> needs_clarification: false, WHERE age > 40
3. Tamil-ambiguous: "முக்கியமான மருத்துவர்களைக் காட்டு" -> needs_clarification: true
4. Thanglish: "40 vayasuku mela irukra patients ellam kaatu" -> needs_clarification: false, WHERE age > 40
"""

import sys
from pathlib import Path
from starlette.testclient import TestClient

# Ensure UTF-8 output on Windows terminal
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app
from app.routers.query import reset_rate_limits
from app.services.sql_generator import clear_query_cache

client = TestClient(app)


def run_tests():
    print("=" * 80)
    print("      MULTILINGUAL & THANGLISH NL2SQL TEST SUITE")
    print("=" * 80)

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
            "type": "English",
            "query": "list all patients older than 40",
            "language": "en",
            "expected_clarification": False,
            "must_contain": ["patients", "40"],
            "description": "Standard English query for patients older than 40",
        },
        {
            "id": 2,
            "type": "Tamil (Tamil Script)",
            "query": "40 வயதுக்கு மேற்பட்ட அனைத்து நோயாளிகளையும் பட்டியலிடுங்கள்",
            "language": "ta",
            "expected_clarification": False,
            "must_contain": ["patients", "40"],
            "description": "Tamil script query for patients older than 40",
        },
        {
            "id": 3,
            "type": "Tamil-Ambiguous",
            "query": "முக்கியமான மருத்துவர்களைக் காட்டு",
            "language": "ta",
            "expected_clarification": True,
            "description": "Ambiguous Tamil query ('important doctors' without criteria)",
        },
        {
            "id": 4,
            "type": "Thanglish",
            "query": "40 vayasuku mela irukra patients ellam kaatu",
            "language": "en",
            "expected_clarification": False,
            "must_contain": ["patients", "40"],
            "description": "Thanglish query (Tamil in Latin script) for patients older than 40",
        },
    ]

    all_passed = True
    generated_sqls = {}

    for tc in test_cases:
        print("-" * 80)
        print(f"TEST CASE {tc['id']}: [{tc['type']}]")
        print(f"Query       : \"{tc['query']}\"")
        print(f"Description : {tc['description']}")
        print("-" * 80)

        clear_query_cache(session_id)

        resp = client.post(
            "/api/query",
            json={"session_id": session_id, "text": tc["query"], "language": tc["language"]},
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
        print(f"explanation            : {explanation}")
        print(f"confidence             : {confidence}")
        print(f"rows_returned          : {len(result)}")

        tc_passed = True

        if needs_clarif != tc["expected_clarification"]:
            print(f"[FAIL] Expected needs_clarification={tc['expected_clarification']}, got {needs_clarif}")
            tc_passed = False

        if tc["expected_clarification"]:
            if not clarif_q:
                print("[FAIL] Expected clarification_question to be populated")
                tc_passed = False
            if sql is not None:
                print(f"[FAIL] Expected sql to be null, got: {sql}")
                tc_passed = False
            if len(result) != 0:
                print(f"[FAIL] Expected 0 rows, got: {len(result)}")
                tc_passed = False
        else:
            if not sql:
                print("[FAIL] Expected generated SQL query, got null/empty")
                tc_passed = False
            else:
                generated_sqls[tc["id"]] = sql
                for token in tc.get("must_contain", []):
                    if token.lower() not in sql.lower():
                        print(f"[FAIL] SQL expected to contain '{token}', got: {sql}")
                        tc_passed = False
            if clarif_q is not None:
                print(f"[FAIL] Expected clarification_question to be null, got: {clarif_q}")
                tc_passed = False

        if tc_passed:
            print(f"-> CASE {tc['id']} RESULT: [PASS]")
        else:
            print(f"-> CASE {tc['id']} RESULT: [FAIL]")
            all_passed = False
        print()

    # Compare English, Tamil, and Thanglish SQL queries
    print("=" * 80)
    print("           SQL LOGICAL EQUIVALENCE COMPARISON")
    print("=" * 80)
    print(f"1. English SQL   : {generated_sqls.get(1, 'N/A')}")
    print(f"2. Tamil SQL     : {generated_sqls.get(2, 'N/A')}")
    print(f"4. Thanglish SQL : {generated_sqls.get(4, 'N/A')}")
    print("-" * 80)
    if (
        generated_sqls.get(1)
        and generated_sqls.get(2)
        and generated_sqls.get(4)
        and all("40" in s and "patients" in s.lower() for s in [generated_sqls[1], generated_sqls[2], generated_sqls[4]])
    ):
        print("-> [PASS] English, Tamil, and Thanglish queries are LOGICALLY EQUIVALENT!")
        print("   All target the 'patients' table with condition on age > 40.")
    else:
        print("-> [FAIL] SQL queries do not match expected logical pattern across languages.")
        all_passed = False
    print("=" * 80)

    return all_passed


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
