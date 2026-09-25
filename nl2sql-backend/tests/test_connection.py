"""
tests/test_connection.py
------------------------
Tests for /api/connect-db and /api/session-status endpoints.
Derived from test_phase2.py, test_phase3.py.
"""

import pytest


class TestDemoConnection:
    """Tests for connecting to the built-in demo databases."""

    def test_connect_hospital_returns_200(self, client):
        resp = client.post("/api/connect-db", json={"db_type": "demo", "demo_name": "hospital"})
        assert resp.status_code == 200

    def test_connect_hospital_returns_session_id(self, client):
        resp = client.post("/api/connect-db", json={"db_type": "demo", "demo_name": "hospital"})
        data = resp.json()
        assert "session_id" in data
        assert len(data["session_id"]) > 0

    def test_connect_hospital_exposes_expected_tables(self, client):
        resp = client.post("/api/connect-db", json={"db_type": "demo", "demo_name": "hospital"})
        tables = resp.json()["tables"]
        assert "patients" in tables
        assert "doctors" in tables
        assert "appointments" in tables

    def test_connect_ecommerce_returns_200(self, client):
        resp = client.post("/api/connect-db", json={"db_type": "demo", "demo_name": "ecommerce"})
        assert resp.status_code == 200

    def test_connect_ecommerce_exposes_ecommerce_tables(self, client):
        resp = client.post("/api/connect-db", json={"db_type": "demo", "demo_name": "ecommerce"})
        tables = resp.json()["tables"]
        # ecommerce demo must have at minimum orders or products
        assert any(t in tables for t in ("orders", "products", "customers"))

    def test_connect_each_call_creates_distinct_session_id(self, client):
        r1 = client.post("/api/connect-db", json={"db_type": "demo", "demo_name": "hospital"})
        r2 = client.post("/api/connect-db", json={"db_type": "demo", "demo_name": "hospital"})
        assert r1.json()["session_id"] != r2.json()["session_id"]

    def test_session_status_valid_after_connect(self, client, hospital_sid):
        resp = client.get(f"/api/session-status?session_id={hospital_sid}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is True
        assert data["session_id"] == hospital_sid

    def test_session_status_invalid_for_unknown_id(self, client):
        resp = client.get("/api/session-status?session_id=nonexistent-uuid-000")
        assert resp.status_code == 200
        data = resp.json()
        assert data["valid"] is False
