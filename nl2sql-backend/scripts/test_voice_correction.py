"""Test script for lightweight voice transcript correction and additive interpreted_text field."""

import sys
from pathlib import Path
from starlette.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app
from app.routers.query import reset_rate_limits
from app.services.sql_generator import clear_query_cache

client = TestClient(app)


def test_transcript_correction():
    print("=" * 80)
    print("        TESTING VOICE TRANSCRIPT CORRECTION & INTERPRETED_TEXT")
    print("=" * 80)

    reset_rate_limits()
    clear_query_cache()

    # Step 1: Connect to demo hospital database
    conn_resp = client.post("/api/connect-db", json={"db_type": "demo", "demo_name": "hospital"})
    assert conn_resp.status_code == 200, f"Connect failed: {conn_resp.text}"
    session_id = conn_resp.json()["session_id"]
    print(f"Connected to demo hospital DB. Session ID: {session_id}\n")

    # Test Case 1: Deliberately misheard voice transcript
    misheard_query = "shom me pashents older then fourty"
    print(f"--- Test Case 1: Misheard voice transcript ---")
    print(f"Raw Input: '{misheard_query}'")

    resp1 = client.post("/api/query", json={
        "session_id": session_id,
        "text": misheard_query,
        "language": "auto"
    })

    print(f"Status Code: {resp1.status_code}")
    data1 = resp1.json()

    # Verify all expected contract fields are present (additive verification)
    expected_fields = [
        "query_id", "sql", "explanation", "confidence",
        "needs_clarification", "clarification_question",
        "query_type", "result", "chart_type", "interpreted_text"
    ]
    for field in expected_fields:
        assert field in data1, f"Missing field in response: {field}"

    interpreted1 = data1.get("interpreted_text", "")
    sql1 = data1.get("sql", "")
    explanation1 = data1.get("explanation", "")
    needs_clarif1 = data1.get("needs_clarification")

    print(f"Interpreted Text: '{interpreted1}'")
    print(f"Generated SQL:    {sql1}")
    print(f"Needs Clarif:     {needs_clarif1}")
    print(f"Explanation:      {explanation1}")
    print(f"Confidence:       {data1.get('confidence')}")

    # Assertions
    assert "show me patients older than forty" in interpreted1.lower() or ("patients" in interpreted1.lower() and "forty" in interpreted1.lower() or "40" in interpreted1.lower()), (
        f"Expected interpreted_text to resolve 'shom me pashents older then fourty' to intended sentence, got: {interpreted1}"
    )
    assert not needs_clarif1, "Should not require clarification"
    assert "patients" in sql1.lower() and ("40" in sql1 or "forty" in sql1), f"SQL should filter patients > 40: {sql1}"
    print(">>> Test Case 1 PASSED!\n")

    # Test Case 2: Clean typed input (regression check)
    clean_query = "show me patients older than 40"
    print(f"--- Test Case 2: Clean typed input ---")
    print(f"Raw Input: '{clean_query}'")

    resp2 = client.post("/api/query", json={
        "session_id": session_id,
        "text": clean_query,
        "language": "auto"
    })
    data2 = resp2.json()
    interpreted2 = data2.get("interpreted_text", "")
    sql2 = data2.get("sql", "")

    print(f"Interpreted Text: '{interpreted2}'")
    print(f"Generated SQL:    {sql2}")

    assert "patients" in interpreted2.lower()
    assert "patients" in sql2.lower() and "40" in sql2
    print(">>> Test Case 2 PASSED!\n")

    print("=" * 80)
    print("ALL VOICE CORRECTION & CONTRACT TESTS PASSED SUCCESSFULLY!")
    print("=" * 80)


if __name__ == "__main__":
    test_transcript_correction()
