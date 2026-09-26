"""SQLite concrete database adapter implementing BaseDatabaseAdapter.

Handles connection, complete schema extraction (PKs, FKs, nullability, sample values, row counts),
safe query execution, and transactional write operations.
"""

import re
import sqlite3
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from app.database.base import BaseDatabaseAdapter

logger = logging.getLogger(__name__)

# Pattern to detect server filesystem paths (Windows drive letters, Unix roots, or .db file references)
_FILE_PATH_RE = re.compile(
    r"(?:[a-zA-Z]:[\\/][^\s:\"',;)]+|/(?:home|app|tmp|var|usr|etc|root|data)/[^\s:\"',;)]+|[\w./\\]+\.(?:db|sqlite|sqlite3)\b)",
    re.IGNORECASE,
)


class SQLiteAdapter(BaseDatabaseAdapter):
    """Concrete adapter for SQLite databases."""

    def __init__(self, db_path: Optional[Union[str, Path]] = None, database_url: Optional[str] = None):
        if db_path is not None:
            self.db_path = Path(db_path)
        elif database_url:
            path_part = database_url.replace("sqlite:///", "")
            self.db_path = Path(path_part)
        else:
            raise ValueError("Either db_path or database_url must be provided for SQLiteAdapter.")
        self.database_url = database_url or f"sqlite:///{self.db_path.as_posix()}"
        self._conn: Optional[sqlite3.Connection] = None

    def connect(self) -> None:
        """Establish or refresh SQLite connection."""
        if not self.db_path.exists():
            raise FileNotFoundError(f"SQLite database file not found at: {self.db_path}")
        self._conn = sqlite3.connect(
            str(self.db_path),
            check_same_thread=False,
            timeout=15.0,
        )
        self._conn.row_factory = sqlite3.Row

    def disconnect(self) -> None:
        """Close active SQLite connection."""
        if self._conn:
            try:
                self._conn.close()
            except Exception:
                pass
            finally:
                self._conn = None

    def validate_connection(self) -> bool:
        """Verify that the database file exists and accepts queries."""
        try:
            if not self.db_path.exists():
                return False
            conn = sqlite3.connect(str(self.db_path), timeout=5.0)
            cur = conn.cursor()
            cur.execute("SELECT 1;")
            cur.fetchone()
            cur.close()
            conn.close()
            return True
        except Exception as exc:
            logger.warning("SQLite connection validation failed for %s: %s", self.db_path, exc)
            return False

    def get_tables(self) -> List[str]:
        """Return list of user tables (excluding sqlite internal tables)."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        try:
            cur = conn.cursor()
            cur.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name;"
            )
            tables = [row[0] for row in cur.fetchall()]
            cur.close()
            return tables
        finally:
            conn.close()

    def get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """Return columns metadata: name, type, nullable, primary_key."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        try:
            cur = conn.cursor()
            safe_table = table_name.replace('"', '""')
            cur.execute(f'PRAGMA table_info("{safe_table}");')
            # PRAGMA table_info: (cid, name, type, notnull, dflt_value, pk)
            rows = cur.fetchall()
            cur.close()
            cols = []
            for r in rows:
                cols.append({
                    "name": r[1],
                    "type": r[2] or "TEXT",
                    "nullable": bool(r[3] == 0),
                    "primary_key": bool(r[5] > 0),
                })
            return cols
        finally:
            conn.close()

    def get_primary_keys(self, table_name: str) -> List[str]:
        """Return list of primary key column names."""
        cols = self.get_columns(table_name)
        return [c["name"] for c in cols if c.get("primary_key")]

    def get_foreign_keys(self, table_name: str) -> List[Dict[str, Any]]:
        """Return foreign key relations via PRAGMA foreign_key_list."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        try:
            cur = conn.cursor()
            safe_table = table_name.replace('"', '""')
            cur.execute(f'PRAGMA foreign_key_list("{safe_table}");')
            # (id, seq, table, from, to, on_update, on_delete, match)
            rows = cur.fetchall()
            cur.close()
            fks = []
            for r in rows:
                fks.append({
                    "constrained_column": r[3],
                    "referred_table": r[2],
                    "referred_column": r[4],
                })
            return fks
        finally:
            conn.close()

    def get_sample_values(self, table_name: str, col_name: str, limit: int = 5) -> List[Any]:
        """Fetch distinct non-null, non-empty sample values."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        try:
            cur = conn.cursor()
            safe_col = col_name.replace('"', '""')
            safe_table = table_name.replace('"', '""')
            query = (
                f'SELECT DISTINCT "{safe_col}" FROM "{safe_table}" '
                f'WHERE "{safe_col}" IS NOT NULL AND TRIM(CAST("{safe_col}" AS TEXT)) != "" '
                f'LIMIT {limit};'
            )
            rows = cur.execute(query).fetchall()
            cur.close()
            samples = []
            for r in rows:
                val = r[0]
                if isinstance(val, str) and len(val) > 60:
                    val = val[:57] + "..."
                samples.append(val)
            return samples
        except Exception as exc:
            logger.warning("Could not fetch samples for %s.%s: %s", table_name, col_name, exc)
            return []
        finally:
            conn.close()

    def get_row_count(self, table_name: str) -> int:
        """Fetch total row count of a table."""
        conn = sqlite3.connect(str(self.db_path), timeout=10.0)
        try:
            cur = conn.cursor()
            safe_table = table_name.replace('"', '""')
            cur.execute(f'SELECT COUNT(*) FROM "{safe_table}";')
            count = cur.fetchone()[0]
            cur.close()
            return int(count)
        except Exception as exc:
            logger.warning("Could not fetch row count for table %s: %s", table_name, exc)
            return 0
        finally:
            conn.close()

    def extract_full_schema(self, sample_limit: int = 5) -> Dict[str, Any]:
        """Extract complete normalized schema including PKs, FKs, nullability, row counts, and samples."""
        tables = self.get_tables()
        schema_dict: Dict[str, List[Dict[str, Any]]] = {}
        sample_values_map: Dict[str, Dict[str, List[Any]]] = {}
        relationships: List[Dict[str, str]] = []
        row_counts: Dict[str, int] = {}
        primary_keys_map: Dict[str, List[str]] = {}

        for tbl in tables:
            cols = self.get_columns(tbl)
            sample_values_map[tbl] = {}
            primary_keys_map[tbl] = []

            for c in cols:
                c_name = c["name"]
                samples = self.get_sample_values(tbl, c_name, limit=sample_limit)
                sample_values_map[tbl][c_name] = samples
                c["sample_values"] = samples
                if c.get("primary_key"):
                    primary_keys_map[tbl].append(c_name)

            schema_dict[tbl] = cols
            row_counts[tbl] = self.get_row_count(tbl)

            # Extract FK relationships
            fks = self.get_foreign_keys(tbl)
            for fk in fks:
                relationships.append({
                    "from_table": tbl,
                    "from_column": fk["constrained_column"],
                    "to_table": fk["referred_table"],
                    "to_column": fk["referred_column"],
                })

        return {
            "tables": tables,
            "schema": schema_dict,
            "sample_values": sample_values_map,
            "relationships": relationships,
            "row_counts": row_counts,
            "primary_keys": primary_keys_map,
            "db_path": self.db_path,
            "database_url": f"sqlite:///{self.db_path.as_posix()}",
        }

    def execute_query(self, sql: str) -> Union[List[Dict[str, Any]], Dict[str, str]]:
        """Execute one or more read (SELECT) queries and return combined list of dicts, or error dict."""
        conn = None
        try:
            from app.services.execution_engine import split_sql_statements
            conn = sqlite3.connect(str(self.db_path), timeout=15.0)
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            stmts = split_sql_statements(sql)
            all_rows = []
            for s in stmts:
                cur.execute(s)
                rows = cur.fetchall()
                if rows:
                    all_rows.extend([dict(row) for row in rows])
            cur.close()
            return all_rows
        except Exception as exc:
            logger.error("SQLite query execution error on %s: %s", self.db_path, exc, exc_info=True)
            err_msg = str(exc)
            db_path_str = str(self.db_path)
            if db_path_str in err_msg:
                err_msg = err_msg.replace(db_path_str, "[database]")
            err_msg = _FILE_PATH_RE.sub("[database]", err_msg)
            return {"error": err_msg}
        finally:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass

    def execute_write(self, sql: str) -> Dict[str, Any]:
        """Execute one or more write statements (INSERT, UPDATE, DELETE) inside a transactional block."""
        conn = None
        try:
            from app.services.execution_engine import split_sql_statements, check_duplicate_insert
            conn = sqlite3.connect(str(self.db_path), timeout=15.0)
            with conn:  # Automatically commits on exit or rolls back on exception
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
                        continue

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
            logger.error("SQLite write execution error on %s: %s", self.db_path, exc, exc_info=True)
            err_msg = str(exc)
            db_path_str = str(self.db_path)
            if db_path_str in err_msg:
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
