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


def validate_sql(sql_string: str, allow_write: bool = False) -> Dict[str, Any]:
    """Validate that the SQL string has valid syntax and permitted statement types.

    Default: READ ONLY (SELECT only).
    When allow_write=True: Permits safe INSERT, UPDATE (with WHERE), and DELETE (with WHERE).
    Strictly forbids:
    - Stacked/multi-statement injection:  SELECT 1; DROP TABLE patients;
    - Comment-based bypass:               SELECT 1 -- ; DROP TABLE patients
    - Block-comment bypass:               SELECT 1 /* ; */ DROP TABLE patients
    - DDL / destructive queries:          DROP, CREATE, ALTER, TRUNCATE
    - UPDATE / DELETE without WHERE clause
    - Empty or whitespace-only input

    Returns:
        dict:
            - {"valid": True, "statement_type": "select"|"insert"|"update"|"delete", "is_write": bool}
            - {"valid": False, "reason": "syntax_error"|"write_not_supported"|"injection_detected"|"missing_where_clause", "message": "..."}
    """
    if not sql_string or not isinstance(sql_string, str) or not sql_string.strip():
        return {
            "valid": False,
            "reason": "syntax_error",
            "message": "The generated SQL had invalid syntax.",
        }

    # ------------------------------------------------------------------
    # Guard 1: SQL comment syntax outside quoted string literals.
    # ------------------------------------------------------------------
    without_strings = _strip_strings(sql_string)
    if "--" in without_strings or "/*" in without_strings:
        return {
            "valid": False,
            "reason": "injection_detected",
            "message": "SQL comment syntax is not allowed in queries.",
        }

    # ------------------------------------------------------------------
    # Guard 2: sqlglot AST parse — syntax and multi-statement validation.
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

    # Multi-statement and statement-type validation
    has_write = False
    statement_types = []

    for stmt in statements:
        # Check for DDL / destructive operations
        if isinstance(stmt, (exp.Drop, exp.Create, exp.Alter, exp.TruncateTable)):
            if len(statements) > 1:
                return {
                    "valid": False,
                    "reason": "injection_detected",
                    "message": "Destructive DDL operations are not allowed in queries.",
                }
            return {
                "valid": False,
                "reason": "write_not_supported",
                "message": "DDL and destructive operations are strictly prohibited.",
            }

        if isinstance(stmt, (exp.Select, exp.Query)):
            statement_types.append("select")
            continue

        # If statement is write (INSERT, UPDATE, DELETE):
        if not allow_write:
            if len(statements) > 1:
                return {
                    "valid": False,
                    "reason": "injection_detected",
                    "message": "Write operations are not permitted in read-only mode.",
                }
            return {
                "valid": False,
                "reason": "write_not_supported",
                "message": "This version only supports read (SELECT) queries.",
            }

        has_write = True
        if isinstance(stmt, exp.Insert):
            statement_types.append("insert")
        elif isinstance(stmt, exp.Update):
            if not stmt.find(exp.Where):
                return {
                    "valid": False,
                    "reason": "missing_where_clause",
                    "message": "UPDATE queries must include a WHERE clause for safety.",
                }
            statement_types.append("update")
        elif isinstance(stmt, exp.Delete):
            if not stmt.find(exp.Where):
                return {
                    "valid": False,
                    "reason": "missing_where_clause",
                    "message": "DELETE queries must include a WHERE clause for safety.",
                }
            statement_types.append("delete")
        else:
            return {
                "valid": False,
                "reason": "write_not_supported",
                "message": "Unsupported SQL statement type.",
            }

    if statement_types:
        if len(set(statement_types)) == 1:
            primary_type = statement_types[0]
        else:
            primary_type = "write" if has_write else "select"
    else:
        primary_type = "select"

    return {
        "valid": True,
        "statement_type": primary_type,
        "is_write": has_write,
        "statements_count": len(statements),
    }


def validate_write_sql(sql_string: str) -> Dict[str, Any]:
    """Helper to validate write queries specifically."""
    return validate_sql(sql_string, allow_write=True)

