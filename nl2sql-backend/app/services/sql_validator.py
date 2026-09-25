import re
from typing import Dict, Any
import sqlglot
from sqlglot import exp


# ---------------------------------------------------------------------------
# Comment-stripped injection pre-check
# ---------------------------------------------------------------------------
# Regex patterns used to strip SQL comments and string literals before counting semicolons.
_LINE_COMMENT_RE = re.compile(r"--[^\n]*", re.MULTILINE)
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.DOTALL)
_STRING_LITERAL_RE = re.compile(r"'(?:\\.|''|[^'\\])*'")
_DOUBLE_QUOTE_RE = re.compile(r'"(?:\\.|""|[^"\\])*"')


def _strip_strings(sql: str) -> str:
    """Remove quoted string literals from SQL text so contents are not mistaken for comments."""
    sql = _STRING_LITERAL_RE.sub("''", sql)
    sql = _DOUBLE_QUOTE_RE.sub('""', sql)
    return sql


def _strip_comments_and_strings(sql: str) -> str:
    """Remove comments and quoted string literals from SQL text for structural analysis."""
    sql = _LINE_COMMENT_RE.sub(" ", sql)
    sql = _BLOCK_COMMENT_RE.sub(" ", sql)
    return _strip_strings(sql)


def validate_sql(sql_string: str) -> Dict[str, Any]:
    """Validate that the SQL string has valid syntax and is exclusively a read (SELECT) query.

    Guards against:
    - Stacked/multi-statement injection:  SELECT 1; DROP TABLE patients;
    - Comment-based bypass:               SELECT 1 -- ; DROP TABLE patients
    - Block-comment bypass:               SELECT 1 /* ; */ DROP TABLE patients
    - Any non-SELECT statement (INSERT, UPDATE, DELETE, DROP, CREATE, …)
    - Empty or whitespace-only input

    Returns:
        dict:
            - {"valid": True} if valid single SELECT query.
            - {"valid": False, "reason": "syntax_error",       "message": "..."}
            - {"valid": False, "reason": "write_not_supported","message": "..."}
            - {"valid": False, "reason": "injection_detected", "message": "..."}
    """
    if not sql_string or not isinstance(sql_string, str) or not sql_string.strip():
        return {
            "valid": False,
            "reason": "syntax_error",
            "message": "The generated SQL had invalid syntax.",
        }

    # ------------------------------------------------------------------
    # Guard 1: Multi-statement check.
    # Strip comments and string literals first, then check whether the
    # remaining text contains more than one semicolon-delimited segment.
    # ------------------------------------------------------------------
    cleaned = _strip_comments_and_strings(sql_string)
    segments = [s.strip() for s in cleaned.split(";") if s.strip()]
    if len(segments) > 1:
        return {
            "valid": False,
            "reason": "injection_detected",
            "message": "Multi-statement SQL is not allowed. Only a single SELECT query is permitted.",
        }

    # ------------------------------------------------------------------
    # Guard 2: SQL comment syntax outside quoted string literals.
    # Strip string literals first so legitimate values containing '--' or '/*'
    # (e.g. WHERE code = '--') are not rejected as false positives.
    # This catches injection attacks like: "SELECT * FROM patients -- ; DROP TABLE patients"
    # ------------------------------------------------------------------
    without_strings = _strip_strings(sql_string)
    if "--" in without_strings or "/*" in without_strings:
        return {
            "valid": False,
            "reason": "injection_detected",
            "message": "SQL comment syntax is not allowed in queries.",
        }

    # ------------------------------------------------------------------
    # Guard 3: sqlglot AST parse — syntax and statement-type validation.
    # ------------------------------------------------------------------
    try:
        parsed_statements = sqlglot.parse(sql_string.strip(), read="sqlite")
        statements = [stmt for stmt in parsed_statements if stmt is not None]
        if not statements:
            return {
                "valid": False,
                "reason": "syntax_error",
                "message": "The generated SQL had invalid syntax.",
            }
    except Exception:
        return {
            "valid": False,
            "reason": "syntax_error",
            "message": "The generated SQL had invalid syntax.",
        }

    # Exactly one statement, and it must be a SELECT
    if len(statements) != 1:
        return {
            "valid": False,
            "reason": "injection_detected",
            "message": "Multi-statement SQL is not allowed. Only a single SELECT query is permitted.",
        }

    if not isinstance(statements[0], (exp.Select, exp.Query)):
        return {
            "valid": False,
            "reason": "write_not_supported",
            "message": "This version only supports read (SELECT) queries.",
        }

    return {"valid": True}

