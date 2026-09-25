"""
tests/test_health.py
--------------------
Smoke tests for the /health endpoint and app startup.
Zero dependencies — pure HTTP, no Gemini, no DB writes.
"""


class TestHealth:
    def test_health_returns_200(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200

    def test_health_returns_ok_status(self, client):
        data = client.get("/health").json()
        assert data.get("status") == "ok"

    def test_health_content_type_is_json(self, client):
        resp = client.get("/health")
        assert "application/json" in resp.headers.get("content-type", "")
