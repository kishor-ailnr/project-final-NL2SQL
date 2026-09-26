"""Universal database execution engine for SELECT and transactional write queries.

Leverages DatabaseConnectionManager and adapters (SQLite, PostgreSQL) while maintaining
full backward compatibility with direct session db_path connections.
"""

import re
import logging
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Union, Optional

from app.services.session_store import get_session

logger = logging.getLogger(__name__)

# Pattern to detect server filesystem paths (Windows drive letters, Unix roots, or .db file references)
_FILE_PATH_RE = re.compile(
    r"(?:[a-zA-Z]:[\\/][^\s:\"',;)]+|/(?:home|app|tmp|var|usr|etc|root|data)/[^\s:\"',;)]+|[\w./\\]+\.(?:db|sqlite|sqlite3)\b)",
    re.IGNORECASE,
)


def split_sql_statements(sql: str) -> List[str]:
    """Split SQL string into individual executable statements using sqlglot or semicolon splitting."""
    try:
        import sqlglot
        parsed = sqlglot.parse(sql.strip(), read="sqlite")
        stmts = [s.sql(dialect="sqlite").strip() for s in parsed if s is not None]
        if stmts:
            return stmts
    except Exception:
        pass
    return [s.strip() for s in sql.split(";") if s.strip()]


def run_select(session_id: str, sql: str) -> Union[List[Dict[str, Any]], Dict[str, str]]:
    """Execute a read (SELECT) SQL query against the session's connected database.
    
    Supports single or multiple SELECT queries executed in sequence.
    Returns:
        List of dicts representing row data, or a dict with an 'error' key on failure.
    """
    # 1. Attempt execution via universal DatabaseConnectionManager adapter
    try:
        from app.database.manager import DatabaseConnectionManager
        adapter = DatabaseConnectionManager.get_adapter(session_id)
        if adapter:
            return adapter.execute_query(sql)
    except Exception as a_exc:
        logger.warning("Adapter execution failed, falling back to direct connection: %s", a_exc)

    # 2. Fallback to direct SQLite connection
    session = get_session(session_id)
    if not session:
        return {"error": "Active session not found. Please connect to a database first."}

    db_path = session.get("db_path")
    if not db_path or not Path(db_path).exists():
        logger.error("Target database file missing from disk for session '%s' at path: %s", session_id, db_path)
        return {"error": "Database file could not be accessed. Please reconnect to the database."}

    conn = None
    try:
        conn = sqlite3.connect(str(db_path), timeout=15.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        stmts = split_sql_statements(sql)
        all_rows = []
        for s in stmts:
            cursor.execute(s)
            rows = cursor.fetchall()
            if rows:
                all_rows.extend([dict(row) for row in rows])
        cursor.close()
        return all_rows
    except Exception as exc:
        logger.error("Database query execution error for session '%s': %s", session_id, exc, exc_info=True)
        err_msg = str(exc)
        # Avoid leaking server file paths while preserving legitimate error details (e.g. 'datatype mismatch')
        db_path_str = str(db_path) if db_path else ""
        if db_path_str and db_path_str in err_msg:
            err_msg = err_msg.replace(db_path_str, "[database]")
        err_msg = _FILE_PATH_RE.sub("[database]", err_msg)
        return {"error": err_msg}
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass


def check_duplicate_insert(cur: sqlite3.Cursor, sql: str) -> Optional[Dict[str, Any]]:
    """Check if an INSERT statement attempts to insert an exact duplicate row across all specified columns.
    
    If every specified column already has an exact match in the target table, returns a dict with details.
    """
    try:
        import sqlglot
        from sqlglot import exp
        stmt = sqlglot.parse_one(sql.strip(), read="sqlite")
        if not isinstance(stmt, exp.Insert):
            return None

        table = None
        if stmt.this:
            if isinstance(stmt.this, exp.Schema):
                table = stmt.this.this.name if stmt.this.this else None
            elif isinstance(stmt.this, exp.Table):
                table = stmt.this.name

        schema = stmt.find(exp.Schema)
        if not schema or not schema.expressions:
            return None
        cols = [c.name for c in schema.expressions]

        values_node = stmt.find(exp.Values)
        if not values_node or not values_node.expressions:
            return None
        val_exprs = values_node.expressions[0].expressions
        if len(cols) != len(val_exprs):
            return None

        vals = []
        for v in val_exprs:
            if isinstance(v, exp.Literal):
                if v.is_number:
                    try:
                        vals.append(int(v.this) if "." not in v.this else float(v.this))
                    except ValueError:
                        vals.append(v.this)
                else:
                    vals.append(v.this)
            else:
                vals.append(v.sql(dialect="sqlite").strip("'\""))

        where_parts = [f'"{c}" = ?' for c in cols]
        check_query = f'SELECT 1 FROM "{table}" WHERE {" AND ".join(where_parts)} LIMIT 1;'
        cur.execute(check_query, vals)
        existing = cur.fetchone()
        if existing:
            pairs_str = ", ".join(f"{c}={repr(v)}" for c, v in zip(cols, vals))
            return {
                "table": table,
                "columns": cols,
                "values": vals,
                "message": f"Duplicate record detected: A row with identical values ({pairs_str}) already exists in '{table}'. Insertion was skipped to prevent duplicate data.",
            }
    except Exception as e:
        logger.debug("Duplicate check skipped: %s", e)
    return None


def run_write(session_id: str, sql: str) -> Dict[str, Any]:
    """Execute a write statement (INSERT, UPDATE, DELETE) inside a transactional block.
    
    Supports executing multiple write operations sequentially in a single transaction.
    Returns:
        dict: {"success": bool, "status": "executed"|"error", "rows_affected": int, "result": list, "notice": str|None}
    """
    # 1. Attempt execution via universal DatabaseConnectionManager adapter
    try:
        from app.database.manager import DatabaseConnectionManager
        adapter = DatabaseConnectionManager.get_adapter(session_id)
        if adapter:
            return adapter.execute_write(sql)
    except Exception as a_exc:
        logger.warning("Adapter write execution failed, falling back to direct SQLite: %s", a_exc)

    # 2. Fallback to direct SQLite connection with transaction
    session = get_session(session_id)
    if not session:
        return {
            "success": False,
            "status": "error",
            "error": "Active session not found. Please connect to a database first.",
            "rows_affected": 0,
        }

    db_path = session.get("db_path")
    if not db_path or not Path(db_path).exists():
        return {
            "success": False,
            "status": "error",
            "error": "Database file could not be accessed. Please reconnect to the database.",
            "rows_affected": 0,
        }

    conn = None
    try:
        conn = sqlite3.connect(str(db_path), timeout=15.0)
        with conn:  # Context manager guarantees COMMIT on success and ROLLBACK on error
            cur = conn.cursor()
            stmts = split_sql_statements(sql)
            total_affected = 0
            all_rows = []
            duplicate_notices = []
            for s in stmts:
                # Pre-check for duplicate INSERT
                dup = check_duplicate_insert(cur, s)
                if dup:
                    duplicate_notices.append(dup["message"])
                    logger.info("Skipped duplicate INSERT: %s", dup["message"])
                    continue  # Do not execute duplicate insert

                cur.execute(s)
                if cur.description:
                    cols = [d[0] for d in cur.description]
                    fetched = cur.fetchall()
                    if fetched:
                        all_rows.extend([dict(zip(cols, r)) for r in fetched])
                elif cur.rowcount and cur.rowcount > 0:
                    total_affected += cur.rowcount
            cur.close()
        notice_str = " ".join(duplicate_notices) if duplicate_notices else None
        return {
            "success": True,
            "status": "executed",
            "rows_affected": max(0, total_affected),
            "result": all_rows,
            "notice": notice_str,
        }
    except Exception as exc:
        logger.error("Write execution error for session '%s': %s", session_id, exc, exc_info=True)
        err_msg = str(exc)
        db_path_str = str(db_path) if db_path else ""
        if db_path_str and db_path_str in err_msg:
            err_msg = err_msg.replace(db_path_str, "[database]")
        err_msg = _FILE_PATH_RE.sub("[database]", err_msg)
        return {
            "success": False,
            "status": "error",
            "error": err_msg,
            "rows_affected": 0,
        }
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass
