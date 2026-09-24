import logging
import sqlite3
from pathlib import Path
from typing import List, Dict, Any, Union
from app.services.session_store import get_session

logger = logging.getLogger(__name__)


def run_select(session_id: str, sql: str) -> Union[List[Dict[str, Any]], Dict[str, str]]:
    """Execute a SQL query against the session's SQLite database.
    
    Returns:
        List of dicts representing row data, or a dict with an 'error' key on failure.
    """
    session = get_session(session_id)
    if not session:
        return {"error": "Active session not found. Please connect to a database first."}

    db_path = session.get("db_path")
    if not db_path or not Path(db_path).exists():
        logger.error("Target database file missing from disk for session '%s' at path: %s", session_id, db_path)
        return {"error": "Database file could not be accessed. Please reconnect to the database."}

    conn = None
    try:
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute(sql)
        rows = cursor.fetchall()
        return [dict(row) for row in rows]
    except Exception as exc:
        logger.error("Database query execution error for session '%s': %s", session_id, exc, exc_info=True)
        err_msg = str(exc)
        # Avoid leaking server file paths if present in error message
        if "data" in err_msg or "\\" in err_msg or "/" in err_msg:
            err_msg = "Database syntax or execution error."
        return {"error": err_msg}
    finally:
        if conn:
            try:
                conn.close()
            except Exception:
                pass

