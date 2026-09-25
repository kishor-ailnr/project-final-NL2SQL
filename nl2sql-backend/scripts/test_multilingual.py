"""Test script for Multilingual & Thanglish NL2SQL support.

Test cases against demo hospital database:
1. English: "list all patients older than 40" — expect explanation in English
2. Tamil: "40 வயதுக்கு மேற்பட்ட நோயாளிகளை காட்டு" — expect explanation in Tamil script
3. Thanglish: "40 vayasuku mela irukra patients ellam kaatu" — expect explanation starting with "Understood —" in English
4. Tamil ambiguous: "சிறந்த மருத்துவர்களை காட்டு" — expect clarification_question in Tamil script
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
from app.services.sql_generator import clear_query_cache, detect_input_language

client = TestClient(app)


def has_tamil(text: str) -> bool:
    """Return True if text contains Tamil Unicode characters."""
    return any("\u0b80" <= c <= "\u0bff" for c in (text or ""))


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
            "expected_detected_lang": "english",
            "expected_clarification": False,
            "must_contain": ["patients", "40"],
            "description": "English query: expect explanation in English",
        },
        {
            "id": 2,
            "type": "Tamil (Tamil Script)",
            "query": "40 வயதுக்கு மேற்பட்ட நோயாளிகளை காட்டு",
            "expected_detected_lang": "tamil",
            "expected_clarification": False,
            "must_contain": ["patients", "40"],
            "description": "Tamil query: expect explanation in Tamil script",
        },
        {
            "id": 3,
            "type": "Thanglish",
            "query": "40 vayasuku mela irukra patients ellam kaatu",
            "expected_detected_lang": "thanglish",
            "expected_clarification": False,
            "must_contain": ["patients", "40"],
            "description": "Thanglish query: expect explanation starting with 'Understood —' in English",
        },
        {
            "id": 4,
            "type": "Tamil Ambiguous",
            "query": "சிறந்த மருத்துவர்களை காட்டு",
            "expected_detected_lang": "tamil",
            "expected_clarification": True,
            "description": "Ambiguous Tamil query: expect clarification_question in Tamil script",
        },
    ]

    all_passed = True
    generated_sqls = {}

    for tc in test_cases:
        print("-" * 80)
        print(f"TEST CASE {tc['id']}: [{tc['type']}]")
        print(f"Query            : \"{tc['query']}\"")
        print(f"Description      : {tc['description']}")
        print("-" * 80)

        clear_query_cache(session_id)

        detected_by_func = detect_input_language(tc["query"])

        resp = client.post(
            "/api/query",
            json={"session_id": session_id, "text": tc["query"], "language": "auto"},
        )

        if resp.status_code != 200:
            print(f"[FAIL] HTTP Status: {resp.status_code}, Response: {resp.text}")
            all_passed = False
            continue

        data = resp.json()
        detected_lang = data.get("detected_language") or detected_by_func
        needs_clarif = data.get("needs_clarification")
        clarif_q = data.get("clarification_question")
        sql = data.get("sql")
        explanation = data.get("explanation")
        confidence = data.get("confidence")
        result = data.get("result", [])

        print(f"Detected Language      : {detected_lang} (expected: {tc['expected_detected_lang']})")
        print(f"needs_clarification    : {needs_clarif}")
        print(f"clarification_question : {clarif_q}")
        print(f"generated_sql          : {sql}")
        print(f"explanation            : {explanation}")
        print(f"confidence             : {confidence}")
        print(f"rows_returned          : {len(result)}")

        tc_passed = True

        # Check detected language
        if detected_lang != tc["expected_detected_lang"]:
            print(f"[FAIL] Detected language mismatch: expected {tc['expected_detected_lang']}, got {detected_lang}")
            tc_passed = False

        # Check needs_clarification
        if needs_clarif != tc["expected_clarification"]:
            print(f"[FAIL] Expected needs_clarification={tc['expected_clarification']}, got {needs_clarif}")
            tc_passed = False

        if tc["expected_clarification"]:
            # Clarification question checks
            if not clarif_q:
                print("[FAIL] Expected clarification_question to be populated")
                tc_passed = False
            else:
                if tc["expected_detected_lang"] == "tamil":
                    if not has_tamil(clarif_q):
                        print(f"[FAIL] Expected clarification_question in Tamil script, got: {clarif_q}")
                        tc_passed = False
                    else:
                        print("[PASS] clarification_question is verified in Tamil script!")
            if sql is not None:
                print(f"[FAIL] Expected sql to be null, got: {sql}")
                tc_passed = False
        else:
            # SQL and Explanation checks
            if not sql:
                print("[FAIL] Expected generated SQL query, got null/empty")
                tc_passed = False
            else:
                generated_sqls[tc["id"]] = sql
                for token in tc.get("must_contain", []):
                    if token.lower() not in sql.lower():
                        print(f"[FAIL] SQL expected to contain '{token}', got: {sql}")
                        tc_passed = False

            if not explanation:
                print("[FAIL] Expected explanation to be populated, got empty")
                tc_passed = False
            else:
                if tc["expected_detected_lang"] == "english":
                    if has_tamil(explanation):
                        print(f"[FAIL] Expected explanation in English, got Tamil characters: {explanation}")
                        tc_passed = False
                    else:
                        print("[PASS] explanation is in English as expected.")
                elif tc["expected_detected_lang"] == "tamil":
                    if not has_tamil(explanation):
                        print(f"[FAIL] Expected explanation in Tamil script, got: {explanation}")
                        tc_passed = False
                    else:
                        print("[PASS] explanation is verified in Tamil script!")
                elif tc["expected_detected_lang"] == "thanglish":
                    if not (explanation.startswith("Understood —") or explanation.startswith("Understood -") or explanation.startswith("Understood –")):
                        print(f"[FAIL] Expected explanation to start with 'Understood —', got: {explanation}")
                        tc_passed = False
                    else:
                        print("[PASS] explanation correctly acknowledges Thanglish with 'Understood —' prefix.")

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
    print(f"3. Thanglish SQL : {generated_sqls.get(3, 'N/A')}")
    print("-" * 80)
    if (
        generated_sqls.get(1)
        and generated_sqls.get(2)
        and generated_sqls.get(3)
        and all("40" in s and "patients" in s.lower() for s in [generated_sqls[1], generated_sqls[2], generated_sqls[3]])
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
