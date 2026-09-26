"""PostgreSQL database adapter implementing BaseDatabaseAdapter.

Handles PostgreSQL connection validation, schema extraction via information_schema,
and query execution. Adheres strictly to 'Do NOT fake support': validates drivers and
live connections honestly, reporting concrete connection status.
"""

import logging
from typing import Any, Dict, List, Optional, Union
from urllib.parse import urlparse

from app.database.base import BaseDatabaseAdapter

logger = logging.getLogger(__name__)


class PostgreSQLAdapter(BaseDatabaseAdapter):
    """Concrete adapter for PostgreSQL databases."""

    def __init__(self, connection_string: str):
        self.connection_string = connection_string
        self._engine = None

    def _check_driver(self) -> tuple[bool, str]:
        """Check if a PostgreSQL DBAPI driver (psycopg2 or asyncpg) is available in Python environment."""
        try:
            import psycopg2  # noqa: F401
            return True, "psycopg2"
        except ImportError:
            try:
                import asyncpg  # noqa: F401
                return True, "asyncpg"
            except ImportError:
                return False, "Neither 'psycopg2' nor 'asyncpg' driver is installed."

    def connect(self) -> None:
        """Establish connection via SQLAlchemy engine if driver is present."""
        has_driver, driver_or_err = self._check_driver()
        if not has_driver:
            raise RuntimeError(
                f"PostgreSQL connection requires a driver: {driver_or_err} "
                "Please install psycopg2-binary in requirements.txt to connect to live PostgreSQL instances."
            )

        from sqlalchemy import create_engine
        url = self.connection_string
        if url.startswith("postgres://"):
            url = url.replace("postgres://", "postgresql://", 1)

        self._engine = create_engine(url, connect_args={"connect_timeout": 5})

    def disconnect(self) -> None:
        """Dispose SQLAlchemy engine and connection pool."""
        if self._engine:
            try:
                self._engine.dispose()
            except Exception:
                pass
            finally:
                self._engine = None

    def validate_connection(self) -> bool:
        """Attempt a live connection ping to verify host, port, credentials, and database reachability."""
        has_driver, _ = self._check_driver()
        if not has_driver:
            return False

        try:
            self.connect()
            with self._engine.connect() as conn:
                from sqlalchemy import text
                conn.execute(text("SELECT 1;"))
            return True
        except Exception as exc:
            logger.warning("PostgreSQL connection validation failed: %s", exc)
            return False

    def get_tables(self) -> List[str]:
        """Query user tables from information_schema."""
        if not self._engine:
            self.connect()
        from sqlalchemy import text
        with self._engine.connect() as conn:
            res = conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public' AND table_type = 'BASE TABLE' "
                    "ORDER BY table_name;"
                )
            )
            return [row[0] for row in res.fetchall()]

    def get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """Query column definitions from information_schema.columns."""
        if not self._engine:
            self.connect()
        from sqlalchemy import text
        with self._engine.connect() as conn:
            query = text(
                "SELECT column_name, data_type, is_nullable "
                "FROM information_schema.columns "
                "WHERE table_schema = 'public' AND table_name = :tbl "
                "ORDER BY ordinal_position;"
            )
            rows = conn.execute(query, {"tbl": table_name}).fetchall()
            pks = set(self.get_primary_keys(table_name))
            return [
                {
                    "name": r[0],
                    "type": r[1].upper(),
                    "nullable": bool(r[2] == "YES"),
                    "primary_key": r[0] in pks,
                }
                for r in rows
            ]

    def get_primary_keys(self, table_name: str) -> List[str]:
        """Query primary key constraint columns."""
        if not self._engine:
            self.connect()
        from sqlalchemy import text
        with self._engine.connect() as conn:
            query = text(
                """
                SELECT kcu.column_name
                FROM information_schema.table_constraints tc
                JOIN information_schema.key_column_usage kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                WHERE tc.constraint_type = 'PRIMARY KEY'
                  AND tc.table_schema = 'public'
                  AND tc.table_name = :tbl;
                """
            )
            rows = conn.execute(query, {"tbl": table_name}).fetchall()
            return [r[0] for r in rows]

    def get_foreign_keys(self, table_name: str) -> List[Dict[str, Any]]:
        """Query foreign key constraints from information_schema."""
        if not self._engine:
            self.connect()
        from sqlalchemy import text
        with self._engine.connect() as conn:
            query = text(
                """
                SELECT
                    kcu.column_name AS constrained_column,
                    ccu.table_name AS referred_table,
                    ccu.column_name AS referred_column
                FROM information_schema.table_constraints AS tc
                JOIN information_schema.key_column_usage AS kcu
                  ON tc.constraint_name = kcu.constraint_name
                  AND tc.table_schema = kcu.table_schema
                JOIN information_schema.constraint_column_usage AS ccu
                  ON ccu.constraint_name = tc.constraint_name
                  AND ccu.table_schema = tc.table_schema
                WHERE tc.constraint_type = 'FOREIGN KEY'
                  AND tc.table_schema = 'public'
                  AND tc.table_name = :tbl;
                """
            )
            rows = conn.execute(query, {"tbl": table_name}).fetchall()
            return [
                {
                    "constrained_column": r[0],
                    "referred_table": r[1],
                    "referred_column": r[2],
                }
                for r in rows
            ]

    def get_sample_values(self, table_name: str, col_name: str, limit: int = 5) -> List[Any]:
        """Query distinct non-null sample values."""
        if not self._engine:
            self.connect()
        from sqlalchemy import text
        with self._engine.connect() as conn:
            safe_tbl = table_name.replace('"', '""')
            safe_col = col_name.replace('"', '""')
            query = text(
                f'SELECT DISTINCT "{safe_col}" FROM "{safe_tbl}" '
                f'WHERE "{safe_col}" IS NOT NULL '
                f'LIMIT {limit};'
            )
            rows = conn.execute(query).fetchall()
            return [r[0] for r in rows]

    def get_row_count(self, table_name: str) -> int:
        """Query total row count of table."""
        if not self._engine:
            self.connect()
        from sqlalchemy import text
        with self._engine.connect() as conn:
            safe_tbl = table_name.replace('"', '""')
            query = text(f'SELECT COUNT(*) FROM "{safe_tbl}";')
            return int(conn.execute(query).scalar() or 0)

    def extract_full_schema(self, sample_limit: int = 5) -> Dict[str, Any]:
        """Extract complete schema dictionary for PostgreSQL."""
        tables = self.get_tables()
        schema_dict: Dict[str, List[Dict[str, Any]]] = {}
        sample_values_map: Dict[str, Dict[str, List[Any]]] = {}
        relationships: List[Dict[str, str]] = []
        row_counts: Dict[str, int] = {}
        primary_keys_map: Dict[str, List[str]] = {}

        for tbl in tables:
            cols = self.get_columns(tbl)
            sample_values_map[tbl] = {}
            primary_keys_map[tbl] = self.get_primary_keys(tbl)

            for c in cols:
                c_name = c["name"]
                try:
                    samples = self.get_sample_values(tbl, c_name, limit=sample_limit)
                except Exception:
                    samples = []
                sample_values_map[tbl][c_name] = samples
                c["sample_values"] = samples

            schema_dict[tbl] = cols
            try:
                row_counts[tbl] = self.get_row_count(tbl)
            except Exception:
                row_counts[tbl] = 0

            fks = self.get_foreign_keys(tbl)
            for fk in fks:
                relationships.append({
                    "from_table": tbl,
                    "from_column": fk["constrained_column"],
                    "to_table": fk["referred_table"],
                    "to_column": fk["referred_column"],
                })

        parsed = urlparse(self.connection_string)
        db_name = parsed.path.lstrip("/") or "postgres"

        return {
            "tables": tables,
            "schema": schema_dict,
            "sample_values": sample_values_map,
            "relationships": relationships,
            "row_counts": row_counts,
            "primary_keys": primary_keys_map,
            "db_type": "postgresql",
            "database_name": db_name,
            "database_url": self.connection_string,
        }

    def execute_query(self, sql: str) -> Union[List[Dict[str, Any]], Dict[str, str]]:
        """Execute a SELECT query against PostgreSQL."""
        if not self._engine:
            self.connect()
        from sqlalchemy import text
        try:
            with self._engine.connect() as conn:
                res = conn.execute(text(sql))
                keys = list(res.keys())
                rows = res.fetchall()
                return [dict(zip(keys, row)) for row in rows]
        except Exception as exc:
            logger.error("PostgreSQL query error: %s", exc)
            return {"error": str(exc)}

    def execute_write(self, sql: str) -> Dict[str, Any]:
        """Execute an INSERT, UPDATE, or DELETE query within a transaction."""
        if not self._engine:
            self.connect()
        from sqlalchemy import text
        try:
            with self._engine.begin() as conn:
                res = conn.execute(text(sql))
                rows_affected = res.rowcount
            return {
                "success": True,
                "status": "executed",
                "rows_affected": max(0, rows_affected),
            }
        except Exception as exc:
            logger.error("PostgreSQL write error: %s", exc)
            return {
                "success": False,
                "status": "error",
                "error": str(exc),
                "rows_affected": 0,
            }
