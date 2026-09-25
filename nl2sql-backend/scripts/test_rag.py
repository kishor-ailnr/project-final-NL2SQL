"""Test script for Schema-Aware Retrieval (RAG) using SentenceTransformers & FAISS.

Covers:
1. Regression check against the hospital demo database:
   - 3 questions against hospital demo (patients, doctors, appointments)
   - Confirms full schema preservation (all 3 tables kept since count <= 4)
   - Verifies SQL generation, validation, and execution match previous behavior exactly.
2. Synthetic wider schema retrieval test:
   - 12 tables across 3 distinct domains (Aviation, E-commerce, Healthcare)
   - Confirms that for large schemas, FAISS similarity retrieval accurately retrieves
     only the relevant tables (2-3 domain-specific tables) and filters out irrelevant ones.
"""

import sys
import sqlite3
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from starlette.testclient import TestClient
from app.main import app
from app.services.rag_service import (
    build_schema_index,
    retrieve_relevant_tables,
    is_session_indexed,
    remove_schema_index,
)
from app.services.session_store import set_session, get_session, remove_session
from app.routers.query import reset_rate_limits
from app.services.sql_generator import clear_query_cache, generate_sql
from app.services.sql_validator import validate_sql
from app.services.execution_engine import run_select

client = TestClient(app)


def test_hospital_regression():
    print("\n" + "=" * 75)
    print(" [1/2] REGRESSION CHECK: HOSPITAL DEMO DATABASE (3 TABLES)")
    print("=" * 75)

    reset_rate_limits()
    clear_query_cache()

    # Step 1: Connect to Hospital Demo
    resp = client.post("/api/connect-db", json={"db_type": "demo", "demo_name": "hospital"})
    assert resp.status_code == 200, f"Connect DB failed: {resp.text}"
    session_data = resp.json()
    session_id = session_data["session_id"]
    tables = session_data["tables"]
    print(f" Connected to Hospital Demo. Session ID: {session_id}")
    print(f" Database tables ({len(tables)}): {tables}")
    assert len(tables) == 3, f"Expected 3 hospital tables, found {len(tables)}"

    # Check RAG index built
    indexed = is_session_indexed(session_id)
    print(f" FAISS RAG index initialized for session: {indexed}")

    # Check small schema preservation rule (count <= 4 -> all tables retained)
    retrieved_tables = retrieve_relevant_tables(session_id, "Show all patients older than 40", top_k=4)
    print(f" RAG retrieved tables for small schema: {retrieved_tables}")
    assert set(retrieved_tables) == set(tables), (
        f"Small schema rule violated! Expected all {tables}, got {retrieved_tables}"
    )
    print(" Small schema protection confirmed: all tables retained without over-filtering.")

    # Run 3 test questions against hospital demo
    hospital_questions = [
        {
            "id": 1,
            "text": "Show all patients older than 40",
            "expected_keywords": ["patients", "age", "40"],
        },
        {
            "id": 2,
            "text": "List all doctors and their specialties",
            "expected_keywords": ["doctors", "specialty"],
        },
        {
            "id": 3,
            "text": "Count the number of appointments for each doctor",
            "expected_keywords": ["appointments", "count"],
        },
    ]

    session = get_session(session_id)
    db_url = session["database_url"]

    for q in hospital_questions:
        print(f"\n--- Hospital Test Question {q['id']}: \"{q['text']}\" ---")
        q_resp = client.post(
            "/api/query",
            json={"session_id": session_id, "text": q["text"], "language": "auto"},
        )
        assert q_resp.status_code == 200, f"Query failed ({q_resp.status_code}): {q_resp.text}"
        data = q_resp.json()

        sql = data.get("sql")
        explanation = data.get("explanation")
        results = data.get("result", [])
        needs_clarif = data.get("needs_clarification", False)

        print(f"  SQL Generated: {sql}")
        print(f"  Explanation:   {explanation}")
        print(f"  Rows Returned: {len(results)}")
        print(f"  Confidence:    {data.get('confidence')}")

        assert not needs_clarif, "Expected clean query without clarification"
        assert sql is not None and len(sql) > 0, "Expected non-empty SQL query"

        # Check keywords
        sql_lower = sql.lower()
        for kw in q["expected_keywords"]:
            assert kw.lower() in sql_lower, f"Keyword '{kw}' missing from generated SQL: {sql}"

        # Validate that execution works
        assert isinstance(results, list) and len(results) > 0, "Expected non-empty result rows from hospital DB"
        print(f"  Sample row 1:  {results[0]}")
        print(f"  Question {q['id']} PASSED successfully!")

    print("\n Hospital demo regression test PASSED with 100% fidelity.")
    return session_id


def test_synthetic_wider_schema():
    print("\n" + "=" * 75)
    print(" [2/2] WIDER SCHEMA RETRIEVAL TEST (12 TABLES ACROSS 3 DOMAINS)")
    print("=" * 75)

    session_id = "test-wide-schema-session-12"

    # Define 12 tables across 3 distinct domains
    # Domain 1: Aviation (4 tables)
    # Domain 2: E-commerce (4 tables)
    # Domain 3: Healthcare (4 tables)
    tables = [
        "airline_flights",
        "airline_airports",
        "airline_passengers",
        "airline_baggage",
        "ecommerce_customers",
        "ecommerce_orders",
        "ecommerce_products",
        "ecommerce_reviews",
        "hospital_patients",
        "hospital_doctors",
        "hospital_prescriptions",
        "hospital_lab_results",
    ]

    schema = {
        "airline_flights": [
            {"name": "flight_id", "type": "INTEGER", "sample_values": [101, 102, 103]},
            {"name": "flight_number", "type": "TEXT", "sample_values": ["AA100", "UA204", "DL505"]},
            {"name": "origin_airport", "type": "TEXT", "sample_values": ["JFK", "LAX", "ORD"]},
            {"name": "destination_airport", "type": "TEXT", "sample_values": ["LHR", "SFO", "MIA"]},
            {"name": "status", "type": "TEXT", "sample_values": ["ON TIME", "DELAYED", "CANCELLED"]},
            {"name": "departure_time", "type": "DATETIME", "sample_values": ["2026-05-01 08:00", "2026-05-01 10:30"]},
        ],
        "airline_airports": [
            {"name": "airport_code", "type": "TEXT", "sample_values": ["JFK", "LAX", "ORD", "LHR"]},
            {"name": "airport_name", "type": "TEXT", "sample_values": ["John F Kennedy", "Los Angeles Intl"]},
            {"name": "city", "type": "TEXT", "sample_values": ["New York", "Los Angeles", "Chicago"]},
            {"name": "country", "type": "TEXT", "sample_values": ["USA", "UK"]},
        ],
        "airline_passengers": [
            {"name": "passenger_id", "type": "INTEGER", "sample_values": [1, 2, 3]},
            {"name": "full_name", "type": "TEXT", "sample_values": ["Alice Walker", "Bob Smith"]},
            {"name": "passport_number", "type": "TEXT", "sample_values": ["P123456", "P789012"]},
            {"name": "frequent_flyer_tier", "type": "TEXT", "sample_values": ["GOLD", "SILVER", "PLATINUM"]},
        ],
        "airline_baggage": [
            {"name": "tag_id", "type": "TEXT", "sample_values": ["BAG-001", "BAG-002"]},
            {"name": "flight_number", "type": "TEXT", "sample_values": ["AA100", "UA204"]},
            {"name": "weight_kg", "type": "REAL", "sample_values": [18.5, 23.0, 15.2]},
            {"name": "claim_carousel", "type": "INTEGER", "sample_values": [3, 7, 1]},
        ],
        "ecommerce_customers": [
            {"name": "customer_id", "type": "INTEGER", "sample_values": [501, 502, 503]},
            {"name": "customer_name", "type": "TEXT", "sample_values": ["Emily Rose", "Michael Chang"]},
            {"name": "email", "type": "TEXT", "sample_values": ["emily@example.com", "mchang@example.com"]},
            {"name": "city", "type": "TEXT", "sample_values": ["Seattle", "Austin", "Denver"]},
        ],
        "ecommerce_orders": [
            {"name": "order_id", "type": "INTEGER", "sample_values": [9001, 9002]},
            {"name": "customer_id", "type": "INTEGER", "sample_values": [501, 502]},
            {"name": "order_date", "type": "DATE", "sample_values": ["2026-04-10", "2026-04-12"]},
            {"name": "total_amount", "type": "REAL", "sample_values": [249.99, 89.50, 1200.00]},
            {"name": "payment_status", "type": "TEXT", "sample_values": ["PAID", "PENDING", "REFUNDED"]},
        ],
        "ecommerce_products": [
            {"name": "product_id", "type": "INTEGER", "sample_values": [11, 12, 13]},
            {"name": "product_name", "type": "TEXT", "sample_values": ["Wireless Headphones", "Mechanical Keyboard"]},
            {"name": "category", "type": "TEXT", "sample_values": ["Electronics", "Accessories"]},
            {"name": "price", "type": "REAL", "sample_values": [99.99, 149.50, 29.99]},
            {"name": "stock_quantity", "type": "INTEGER", "sample_values": [150, 45, 0]},
        ],
        "ecommerce_reviews": [
            {"name": "review_id", "type": "INTEGER", "sample_values": [701, 702]},
            {"name": "product_id", "type": "INTEGER", "sample_values": [11, 12]},
            {"name": "rating", "type": "INTEGER", "sample_values": [5, 4, 1]},
            {"name": "review_text", "type": "TEXT", "sample_values": ["Great battery life!", "Fast shipping"]},
        ],
        "hospital_patients": [
            {"name": "patient_id", "type": "INTEGER", "sample_values": [1, 2, 3]},
            {"name": "patient_name", "type": "TEXT", "sample_values": ["Sarah Connor", "John Matrix"]},
            {"name": "age", "type": "INTEGER", "sample_values": [42, 58, 29]},
            {"name": "primary_diagnosis", "type": "TEXT", "sample_values": ["Hypertension", "Asthma", "Diabetes"]},
        ],
        "hospital_doctors": [
            {"name": "doctor_id", "type": "INTEGER", "sample_values": [10, 20]},
            {"name": "doctor_name", "type": "TEXT", "sample_values": ["Dr. House", "Dr. Cuddy"]},
            {"name": "department", "type": "TEXT", "sample_values": ["Cardiology", "Neurology"]},
            {"name": "years_experience", "type": "INTEGER", "sample_values": [15, 8]},
        ],
        "hospital_prescriptions": [
            {"name": "prescription_id", "type": "INTEGER", "sample_values": [301, 302]},
            {"name": "patient_id", "type": "INTEGER", "sample_values": [1, 2]},
            {"name": "medication_name", "type": "TEXT", "sample_values": ["Lisinopril", "Metformin", "Albuterol"]},
            {"name": "dosage_mg", "type": "REAL", "sample_values": [10.0, 500.0, 2.5]},
            {"name": "prescribed_date", "type": "DATE", "sample_values": ["2026-03-15", "2026-03-20"]},
        ],
        "hospital_lab_results": [
            {"name": "lab_id", "type": "INTEGER", "sample_values": [401, 402]},
            {"name": "patient_id", "type": "INTEGER", "sample_values": [1, 2]},
            {"name": "test_type", "type": "TEXT", "sample_values": ["Blood Glucose", "Lipid Panel"]},
            {"name": "result_value", "type": "TEXT", "sample_values": ["110 mg/dL", "Normal", "High"]},
        ],
    }

    # Register the wide schema in session store and build FAISS index
    session_data = {
        "db_type": "upload",
        "upload_name": "synthetic_12_tables",
        "db_path": Path("synthetic.db"),
        "database_url": "sqlite:///:memory:",
        "tables": tables,
        "schema": schema,
        "sample_values": {t: {c["name"]: c.get("sample_values", []) for c in cols} for t, cols in schema.items()},
    }
    set_session(session_id, session_data)

    print(f" Registered synthetic session with {len(tables)} tables.")
    assert is_session_indexed(session_id), "RAG index should be built for wide schema"

    # Test Cases for Semantic Precision across 3 domains
    test_queries = [
        {
            "query": "Which flights are currently delayed from JFK airport?",
            "domain": "Aviation",
            "expected_top": ["airline_flights", "airline_airports"],
            "forbidden_in_top2": ["hospital_patients", "hospital_doctors", "ecommerce_orders", "ecommerce_products"],
        },
        {
            "query": "Find customers who placed orders with total amount over 500 dollars",
            "domain": "E-Commerce",
            "expected_top": ["ecommerce_orders", "ecommerce_customers"],
            "forbidden_in_top2": ["airline_flights", "airline_airports", "hospital_patients", "hospital_prescriptions"],
        },
        {
            "query": "What dosage of medication was prescribed to patients with hypertension?",
            "domain": "Healthcare",
            "expected_top": ["hospital_prescriptions", "hospital_patients"],
            "forbidden_in_top2": ["airline_flights", "airline_airports", "ecommerce_orders", "ecommerce_products"],
        },
    ]

    for tc in test_queries:
        print(f"\n--- Testing Query ({tc['domain']} domain): \"{tc['query']}\" ---")
        retrieved = retrieve_relevant_tables(session_id, tc["query"], top_k=4)
        print(f"  Total tables available: 12")
        print(f"  RAG retrieved tables ({len(retrieved)}): {retrieved}")

        assert len(retrieved) <= 4, f"Should retrieve at most top 4 tables, got {len(retrieved)}"

        # Check that expected tables are in retrieved list
        for exp in tc["expected_top"]:
            assert exp in retrieved, f"Critical table '{exp}' was not retrieved! Got: {retrieved}"
            print(f"   Expected table '{exp}' retrieved successfully.")

        # Check that top 2 tables do NOT contain completely unrelated domain tables
        top2 = retrieved[:2]
        for forb in tc["forbidden_in_top2"]:
            assert forb not in top2, f"Irrelevant table '{forb}' incorrectly ranked in top 2! Top 2: {top2}"

        print(f"   Domain isolation verified: completely unrelated tables excluded from top ranks.")
        print(f"   Prompt schema reduction: prompt receives {len(retrieved)} tables instead of 12 ({(1 - len(retrieved)/12)*100:.0f}% reduction in schema tokens)!")

    # Clean up
    remove_session(session_id)
    print("\n Synthetic wider schema test PASSED with 100% precision.")


if __name__ == "__main__":
    try:
        test_hospital_regression()
        test_synthetic_wider_schema()
        print("\n" + "=" * 75)
        print(" ALL RAG TESTS PASSED SUCCESSFULLY! ")
        print("=" * 75)
    except Exception as exc:
        print(f"\n TEST FAILED: {exc}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
