"""Test Script: Validating CSV table naming fix and sample values inclusion.

Tests:
1. Table naming verification:
   - "Attendance_Prediction.csv" -> "attendance_prediction"
   - "2024_Student_Records.csv" -> "t_2024_student_records"
   - "Final Results (Semester 1).csv" -> "final_results_semester_1"

2. Upload CSV with text column "year" containing '1st year', '2nd year':
   - Upload file named "Attendance_Prediction.csv" via POST /api/upload-db
   - Verify table name is "attendance_prediction"
   - Verify sample values are populated in session
   - Query: "students in 1st year"
   - Confirm generated SQL uses `year = '1st year'`
   - Confirm executed results return non-empty rows

3. Regression check on existing demo database (hospital):
   - Connect to demo hospital
   - Query: "List all patients older than 40"
   - Confirm query succeeds and returns rows
"""

import sys
import io
import requests
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.routers.connect_db import sanitize_table_name

BASE_URL = "http://127.0.0.1:8000"


def test_table_naming():
    print("=" * 65)
    print("  TEST 1: Table Naming Logic")
    print("=" * 65)
    test_cases = [
        ("Attendance_Prediction.csv", "attendance_prediction"),
        ("2024_Student_Records.csv", "t_2024_student_records"),
        ("Final Results (Semester 1).csv", "final_results_semester_1"),
        ("123.csv", "t_123"),
        ("My-Data_Set#2.csv", "my_data_set_2"),
    ]
    for filename, expected in test_cases:
        actual = sanitize_table_name(filename)
        assert actual == expected, f"Failed for '{filename}': expected '{expected}', got '{actual}'"
        print(f"  [PASS] '{filename}' -> '{actual}'")
    print("All table naming tests PASSED!\n")


def test_upload_and_query():
    print("=" * 65)
    print("  TEST 2: CSV Upload with '1st year' and Query Generation")
    print("=" * 65)

    # Prepare sample CSV content
    csv_content = """student_id,name,year,major,gpa
101,Aarav Sharma,1st year,Computer Science,3.8
102,Diya Patel,2nd year,Data Science,3.9
103,Rohan Verma,1st year,Computer Science,3.5
104,Ananya Gupta,3rd year,Information Technology,3.7
105,Vikram Singh,1st year,Mechanical Engineering,3.4
"""
    csv_bytes = csv_content.encode("utf-8")
    files = {
        "file": ("Attendance_Prediction.csv", io.BytesIO(csv_bytes), "text/csv")
    }

    print("Uploading 'Attendance_Prediction.csv' to /api/upload-db...")
    resp = requests.post(f"{BASE_URL}/api/upload-db", files=files)
    assert resp.status_code == 200, f"Upload failed: {resp.status_code} {resp.text}"
    upload_data = resp.json()
    session_id = upload_data["session_id"]
    tables = upload_data["tables"]

    print(f"  Session ID: {session_id}")
    print(f"  Tables created: {tables}")
    assert "attendance_prediction" in tables, f"Expected table 'attendance_prediction', got {tables}"
    print("  [PASS] Clean table name 'attendance_prediction' verified!")

    # Verify session store schema and samples
    from app.services.session_store import get_session
    from app.services.sql_generator import _format_schema_for_prompt

    session = get_session(session_id)
    assert session is not None, "Session not found in store"
    prompt_schema = _format_schema_for_prompt(session["schema"], session.get("sample_values"))
    print("\nFormatted Schema for Gemini Prompt:")
    print("  " + prompt_schema)
    assert "sample values:" in prompt_schema, "Sample values missing from formatted prompt schema"
    assert "'1st year'" in prompt_schema, "'1st year' sample value missing from prompt schema"
    print("  [PASS] Sample values verified in prompt schema!")

    # Ask natural language query: "students in 1st year"
    print("\nSending query: 'students in 1st year'...")
    query_resp = requests.post(
        f"{BASE_URL}/api/query",
        json={"session_id": session_id, "text": "students in 1st year"}
    )
    assert query_resp.status_code == 200, f"Query failed: {query_resp.status_code} {query_resp.text}"
    query_data = query_resp.json()
    sql = query_data["sql"]
    results = query_data["result"]

    print(f"  Generated SQL: {sql}")
    print(f"  Explanation:   {query_data.get('explanation')}")
    print(f"  Confidence:    {query_data.get('confidence')}")
    print(f"  Result Rows:   {results}")

    # Verify SQL matches text '1st year' instead of numeric 1
    assert "1st year" in sql, f"SQL does not filter by '1st year': {sql}"
    assert len(results) > 0, f"Expected results, got empty: {results}"
    print(f"  [PASS] Query successfully returned {len(results)} rows for '1st year'!\n")


def test_regression_hospital():
    print("=" * 65)
    print("  TEST 3: Regression Check on Demo Database (Hospital)")
    print("=" * 65)
    resp = requests.post(
        f"{BASE_URL}/api/connect-db",
        json={"db_type": "demo", "demo_name": "hospital"}
    )
    assert resp.status_code == 200, f"Connect hospital failed: {resp.status_code}"
    session_id = resp.json()["session_id"]

    query_resp = requests.post(
        f"{BASE_URL}/api/query",
        json={"session_id": session_id, "text": "List all patients older than 40"}
    )
    assert query_resp.status_code == 200, f"Hospital query failed: {query_resp.status_code}"
    query_data = query_resp.json()
    sql = query_data["sql"]
    results = query_data["result"]

    print(f"  Generated SQL: {sql}")
    print(f"  Row Count:     {len(results)}")
    assert len(results) == 6, f"Expected 6 patients older than 40, got {len(results)}"
    print("  [PASS] Demo hospital database regression check PASSED!\n")


if __name__ == "__main__":
    test_table_naming()
    test_upload_and_query()
    test_regression_hospital()
    print("=" * 65)
    print("  ALL TESTS PASSED SUCCESSFULLY!")
    print("=" * 65)
