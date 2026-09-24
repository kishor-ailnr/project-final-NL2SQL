"""Security Verification & Regression Test Suite

Tests:
1. CORS configuration & regex domain restriction
2. Error sanitization (no file paths, stack traces, or internal server info in responses)
3. Git history audit for .env secrets
4. In-memory rate limiting on /api/query (20 req/min per session_id)
"""

import sys
import subprocess
from pathlib import Path
from starlette.testclient import TestClient

BACKEND_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BACKEND_DIR))

from app.main import app
from app.routers.query import reset_rate_limits

client = TestClient(app)


def test_cors():
    print("=" * 65)
    print("  CHECK 1: CORS Configuration & Regex Matching")
    print("=" * 65)

    # 1. Allowed: production Vercel URL
    prod_url = "https://project-final-nl-2-sql.vercel.app"
    r1 = client.get("/health", headers={"Origin": prod_url})
    assert r1.headers.get("access-control-allow-origin") == prod_url, f"Expected {prod_url} allowed"
    print(f"  [PASS] Production Vercel domain allowed: {prod_url}")

    # 1b. Allowed: OPTIONS preflight check for production domain
    r1_preflight = client.options(
        "/api/connect-db",
        headers={
            "Origin": prod_url,
            "Access-Control-Request-Method": "POST",
            "Access-Control-Request-Headers": "content-type",
        },
    )
    assert r1_preflight.headers.get("access-control-allow-origin") == prod_url, "Preflight must return allow-origin"
    print(f"  [PASS] OPTIONS preflight to /api/connect-db allowed for: {prod_url}")

    # 2. Allowed: dynamic preview under kishor-ailnrs-projects.vercel.app
    preview_url = "https://project-final-nl-2-nrfu08t13-kishor-ailnrs-projects.vercel.app"
    r2 = client.get("/health", headers={"Origin": preview_url})
    assert r2.headers.get("access-control-allow-origin") == preview_url, f"Expected {preview_url} allowed"
    print(f"  [PASS] Preview subdomain allowed: {preview_url}")

    # 3. Allowed: localhost
    local_url = "http://localhost:5173"
    r3 = client.get("/health", headers={"Origin": local_url})
    assert r3.headers.get("access-control-allow-origin") == local_url, f"Expected {local_url} allowed"
    print(f"  [PASS] Localhost allowed: {local_url}")

    # 4. Allowed: any Vercel preview domain via regex
    preview_branch = "https://project-final-nl-2-sql-git-main-test.vercel.app"
    r4 = client.get("/health", headers={"Origin": preview_branch})
    assert r4.headers.get("access-control-allow-origin") == preview_branch, f"Expected {preview_branch} allowed"
    print(f"  [PASS] Vercel preview domain allowed via regex: {preview_branch}")

    # 5. BLOCKED: random external domain
    random_domain = "https://malicious-site.com"
    r5 = client.get("/health", headers={"Origin": random_domain})
    assert r5.headers.get("access-control-allow-origin") is None, f"External domain must be blocked"
    print(f"  [PASS] Arbitrary external domain BLOCKED: {random_domain}")
    print("  -> CORS Audit: PASSED (Strictly restricted, no wildcard '*')\n")


def test_error_sanitization():
    print("=" * 65)
    print("  CHECK 2: Error Response Sanitization (No Leakage)")
    print("=" * 65)

    # Missing session check
    r_miss = client.post("/api/query", json={"session_id": "non-existent-session-id", "text": "test"})
    assert r_miss.status_code == 404
    detail = r_miss.json().get("detail", "")
    assert "C:" not in detail and "/" not in detail and "Traceback" not in detail
    print(f"  [PASS] 404 Missing Session error sanitized: '{detail}'")

    # Connect to hospital demo to test query execution error
    r_conn = client.post("/api/connect-db", json={"db_type": "demo", "demo_name": "hospital"})
    assert r_conn.status_code == 200
    session_id = r_conn.json()["session_id"]

    # Test execution engine error response directly
    from app.services.execution_engine import run_select
    exec_err = run_select("fake-id", "SELECT * FROM patients")
    err_text = exec_err.get("error", "")
    assert "C:" not in err_text and "\\" not in err_text
    print(f"  [PASS] Missing database path error sanitized: '{err_text}'")
    print("  -> Error Sanitization Audit: PASSED (Zero server file paths or stack traces leaked)\n")


def test_git_history():
    print("=" * 65)
    print("  CHECK 3: Git History Audit for Secret .env Files")
    print("=" * 65)

    cmd1 = ["git", "log", "--all", "--full-history", "--", ".env"]
    res1 = subprocess.run(cmd1, capture_output=True, text=True, cwd=str(BACKEND_DIR.parent))
    out1 = res1.stdout.strip()
    print(f"  Command: git log --all --full-history -- .env")
    print(f"  Output:  {out1 if out1 else '(empty - no commits found)'}")
    assert out1 == "", f"ALERT: .env found in git history!"

    cmd2 = ["git", "log", "--all", "--full-history", "--", "nl2sql-backend/.env"]
    res2 = subprocess.run(cmd2, capture_output=True, text=True, cwd=str(BACKEND_DIR.parent))
    out2 = res2.stdout.strip()
    print(f"\n  Command: git log --all --full-history -- nl2sql-backend/.env")
    print(f"  Output:  {out2 if out2 else '(empty - no commits found)'}")
    assert out2 == "", f"ALERT: nl2sql-backend/.env found in git history!"

    print("  [PASS] .env file containing GEMINI_API_KEY was NEVER committed to git history!")
    print("  -> Secret Leaks in Git History: PASSED (Clean)\n")


def test_rate_limiting():
    print("=" * 65)
    print("  CHECK 4: Rate Limiting on /api/query (20 req/min)")
    print("=" * 65)

    reset_rate_limits()
    test_session = "rate-limit-test-session-123"

    from app.services.session_store import set_session
    set_session(test_session, {
        "db_type": "demo",
        "demo_name": "hospital",
        "db_path": BACKEND_DIR / "data" / "demo_hospital.db",
        "database_url": f"sqlite:///{(BACKEND_DIR / 'data' / 'demo_hospital.db').as_posix()}",
        "tables": ["patients"],
        "schema": {"patients": [{"name": "id", "type": "INTEGER"}]},
    })

    print("  Sending 20 rapid queries for session 'rate-limit-test-session-123'...")
    # Mocking sql_generator cache to avoid burning Gemini API during 20 rapid requests
    from app.services.sql_generator import _QUERY_CACHE
    for i in range(20):
        _QUERY_CACHE[f"{test_session}:question {i}"] = {
            "sql": "SELECT 1;",
            "explanation": "Test rate limit",
            "confidence": 1.0,
        }
        res = client.post("/api/query", json={"session_id": test_session, "text": f"question {i}"})
        assert res.status_code == 200, f"Request {i+1} failed unexpectedly: {res.status_code}"

    print("  [PASS] 20 legitimate requests within 1 minute succeeded (Status 200).")

    # 21st request must trigger 429
    res_21 = client.post("/api/query", json={"session_id": test_session, "text": "question 21"})
    print(f"  Request 21 Status Code: {res_21.status_code}")
    print(f"  Request 21 Detail:      {res_21.json().get('detail')}")
    print(f"  Retry-After Header:     {res_21.headers.get('retry-after')}")

    assert res_21.status_code == 429, f"Expected 429 Too Many Requests, got {res_21.status_code}"
    assert "Rate limit exceeded" in res_21.json().get("detail", "")
    print("  [PASS] 21st request blocked with HTTP 429 Too Many Requests!")

    # Verify a different session_id is NOT affected
    other_session = "different-session-456"
    set_session(other_session, {
        "db_type": "demo",
        "demo_name": "hospital",
        "db_path": BACKEND_DIR / "data" / "demo_hospital.db",
        "database_url": f"sqlite:///{(BACKEND_DIR / 'data' / 'demo_hospital.db').as_posix()}",
        "tables": ["patients"],
        "schema": {"patients": [{"name": "id", "type": "INTEGER"}]},
    })
    _QUERY_CACHE[f"{other_session}:hello"] = {"sql": "SELECT 1;", "explanation": "ok", "confidence": 1.0}
    res_other = client.post("/api/query", json={"session_id": other_session, "text": "hello"})
    assert res_other.status_code == 200, "Different session should not be throttled"
    print("  [PASS] Unrelated session is unaffected and permitted.")
    print("  -> Rate Limiting: PASSED\n")


if __name__ == "__main__":
    test_cors()
    test_error_sanitization()
    test_git_history()
    test_rate_limiting()
    print("=" * 65)
    print("  ALL 4 SECURITY AUDIT CHECKS COMPLETED AND PASSED!")
    print("=" * 65)
