import sqlite3
import os
from starlette.testclient import TestClient
from app.main import app

with TestClient(app) as client:
    # Connect to demo hospital database
    conn_resp = client.post("/api/connect-db", json={"db_type": "demo", "demo_name": "hospital"})
    assert conn_resp.status_code == 200
    session_id = conn_resp.json()["session_id"]
    db_path = os.path.abspath("data/demo_hospital.db")

    # 1. Direct DB check BEFORE
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, name, age, diagnosis FROM patients WHERE name LIKE '%Pavai%'")
    row_before = cur.fetchall()
    conn.close()

    print(f"STEP 1 [Direct DB SELECT BEFORE]:")
    print(f"  Row: {row_before}")

    # 2. Submit write query
    print(f"\nSTEP 2 [POST /api/query]: 'update the age of patient Pavai to 29'")
    q_resp = client.post("/api/query", json={
        "session_id": session_id,
        "text": "update the age of patient Pavai to 29",
        "language": "auto"
    })
    q_data = q_resp.json()
    print(f"  Status code: {q_resp.status_code}")
    print(f"  Query type: {q_data.get('query_type')}")
    print(f"  Query ID: {q_data.get('query_id')}")
    print(f"  Generated SQL: {q_data.get('sql')}")

    # 3. Confirm write query
    query_id = q_data.get("query_id")
    print(f"\nSTEP 3 [POST /api/confirm-write]: query_id='{query_id}', confirmed=True")
    c_resp = client.post("/api/confirm-write", json={
        "session_id": session_id,
        "query_id": query_id,
        "confirmed": True
    })
    c_data = c_resp.json()
    print(f"  Status code: {c_resp.status_code}")
    print(f"  Status: {c_data.get('status')}")
    print(f"  Rows affected: {c_data.get('rows_affected')}")

    # 4. Direct DB check AFTER
    conn = sqlite3.connect(db_path)
    cur = conn.cursor()
    cur.execute("SELECT id, name, age, diagnosis FROM patients WHERE name LIKE '%Pavai%'")
    row_after = cur.fetchall()
    conn.close()

    print(f"\nSTEP 4 [Direct DB SELECT AFTER]:")
    print(f"  Row: {row_after}")
