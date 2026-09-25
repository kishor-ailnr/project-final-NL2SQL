"""
tests/test_sql_validator.py
---------------------------
Unit tests for app.services.sql_validator.validate_sql().
No server, no Gemini, no network — pure function tests.
Derived from: test_phase3.py Case B, test_security_audit.py, plus the
new injection cases added during the security hardening pass.
"""

import pytest
from app.services.sql_validator import validate_sql


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def _valid(sql: str) -> bool:
    return validate_sql(sql).get("valid", False)


def _reason(sql: str) -> str:
    return validate_sql(sql).get("reason", "")


# ---------------------------------------------------------------------------
# Valid SELECT queries
# ---------------------------------------------------------------------------

class TestValidSelects:
    def test_simple_select_star(self):
        assert _valid("SELECT * FROM patients") is True

    def test_select_with_where(self):
        assert _valid("SELECT * FROM patients WHERE age > 40") is True

    def test_select_with_join(self):
        sql = "SELECT p.name, d.name FROM patients p JOIN appointments a ON p.id = a.patient_id JOIN doctors d ON d.id = a.doctor_id"
        assert _valid(sql) is True

    def test_select_with_group_by_and_having(self):
        sql = "SELECT department, COUNT(*) AS cnt FROM doctors GROUP BY department HAVING cnt > 1"
        assert _valid(sql) is True

    def test_select_with_order_by_limit(self):
        sql = "SELECT name, age FROM patients ORDER BY age DESC LIMIT 5"
        assert _valid(sql) is True

    def test_select_aggregate_avg(self):
        assert _valid("SELECT AVG(age) FROM patients") is True

    def test_select_count_star(self):
        assert _valid("SELECT COUNT(*) FROM doctors") is True

    def test_select_subquery(self):
        sql = "SELECT name FROM patients WHERE age = (SELECT MAX(age) FROM patients)"
        assert _valid(sql) is True


# ---------------------------------------------------------------------------
# Write operations — must be blocked
# ---------------------------------------------------------------------------

class TestWriteOperationsBlocked:
    def test_drop_table_blocked(self):
        assert _valid("DROP TABLE patients") is False

    def test_delete_blocked(self):
        assert _valid("DELETE FROM patients WHERE 1=1") is False

    def test_insert_blocked(self):
        assert _valid("INSERT INTO patients VALUES (1, 'x', 20, 'M', 'flu', '2024-01-01')") is False

    def test_update_blocked(self):
        assert _valid("UPDATE patients SET name='hacked' WHERE 1=1") is False

    def test_create_table_blocked(self):
        assert _valid("CREATE TABLE evil (id INTEGER)") is False

    def test_alter_table_blocked(self):
        assert _valid("ALTER TABLE patients ADD COLUMN secret TEXT") is False

    def test_truncate_blocked(self):
        # sqlglot may parse this differently per dialect; either blocked or syntax_error is fine
        result = validate_sql("TRUNCATE TABLE patients")
        assert result["valid"] is False

    def test_write_reason_is_write_not_supported(self):
        assert _reason("DROP TABLE patients") == "write_not_supported"


# ---------------------------------------------------------------------------
# SQL Injection — multi-statement and comment bypass
# ---------------------------------------------------------------------------

class TestInjectionBlocked:
    def test_stacked_select_plus_drop(self):
        assert _valid("SELECT * FROM patients; DROP TABLE patients;") is False
        assert _reason("SELECT * FROM patients; DROP TABLE patients;") == "injection_detected"

    def test_stacked_select_plus_delete(self):
        assert _valid("SELECT 1; DELETE FROM patients WHERE 1=1;") is False

    def test_line_comment_mid_string_bypass(self):
        # SELECT 1 -- ; DROP TABLE t  — the DROP is hidden behind a -- comment
        assert _valid("SELECT * FROM patients -- ; DROP TABLE patients") is False
        assert _reason("SELECT * FROM patients -- ; DROP TABLE patients") == "injection_detected"

    def test_block_comment_wraps_injection(self):
        assert _valid("SELECT * FROM patients /* ; DROP TABLE patients */") is False
        assert _reason("SELECT * FROM patients /* ; DROP TABLE patients */") == "injection_detected"

    def test_leading_line_comment(self):
        assert _valid("-- DROP TABLE patients\nSELECT 1") is False

    def test_empty_string(self):
        assert _valid("") is False
        assert _reason("") == "syntax_error"

    def test_whitespace_only(self):
        assert _valid("   \t\n  ") is False

    def test_none_input(self):
        # validate_sql should handle None without crashing
        result = validate_sql(None)  # type: ignore[arg-type]
        assert result["valid"] is False

    def test_multiple_semicolons(self):
        assert _valid("SELECT 1; SELECT 2; SELECT 3;") is False


# ---------------------------------------------------------------------------
# Edge cases
# ---------------------------------------------------------------------------

class TestEdgeCases:
    def test_select_with_trailing_semicolon_is_valid(self):
        # A single statement followed by ONE trailing semicolon should be valid
        assert _valid("SELECT * FROM patients;") is True

    def test_select_with_string_literal_containing_semicolon(self):
        # Semicolons inside string literals must not trigger multi-statement guard
        sql = "SELECT * FROM patients WHERE diagnosis = 'Type 2 Diabetes; controlled'"
        assert _valid(sql) is True

    def test_complex_with_cte(self):
        sql = """
        WITH aged AS (SELECT * FROM patients WHERE age > 40)
        SELECT name FROM aged
        """
        assert _valid(sql) is True

    def test_select_with_double_dash_inside_string_literal(self):
        # Double dash inside a string literal is a valid value, not a SQL comment injection (UE-05)
        sql = "SELECT * FROM patients WHERE diagnosis = '-- not specified --'"
        assert _valid(sql) is True

    def test_select_with_block_comment_syntax_inside_string_literal(self):
        sql = "SELECT * FROM patients WHERE diagnosis = '/* pending review */'"
        assert _valid(sql) is True
