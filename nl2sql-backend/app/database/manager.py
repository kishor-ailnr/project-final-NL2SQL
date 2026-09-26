"""Database connection manager and adapter registry.

Orchestrates database adapters, validates connection strings, and provides universal
access to active session database instances.
"""

import logging
from pathlib import Path
from typing import Any, Dict, Optional, Union
from urllib.parse import urlparse

from app.database.base import BaseDatabaseAdapter
from app.database.sqlite_adapter import SQLiteAdapter
from app.database.postgres_adapter import PostgreSQLAdapter

logger = logging.getLogger(__name__)

# Active adapter cache: session_id -> BaseDatabaseAdapter instance
_SESSION_ADAPTERS: Dict[str, BaseDatabaseAdapter] = {}


class DatabaseConnectionManager:
    """Factory and registry for database adapters."""

    @staticmethod
    def create_adapter(
        db_type: str = "sqlite",
        connection_string: Optional[str] = None,
        db_path: Optional[Union[str, Path]] = None,
    ) -> BaseDatabaseAdapter:
        """Instantiate and return the appropriate database adapter based on scheme or parameters."""
        # 1. Direct connection string inspection
        if connection_string:
            cs = connection_string.strip()
            parsed = urlparse(cs)
            scheme = (parsed.scheme or "").lower()

            if scheme in ("postgresql", "postgres"):
                return PostgreSQLAdapter(connection_string=cs)

            if scheme == "sqlite":
                # e.g. sqlite:///path/to/db.db or sqlite:///C:/path/to/db.db
                path_part = cs[len("sqlite:///"):]
                sqlite_path = Path(path_part)
                return SQLiteAdapter(db_path=sqlite_path)

            if scheme == "mysql":
                raise ValueError(
                    "MySQL support requires the 'mysqlclient' or 'pymysql' driver. "
                    "Please provide a SQLite or PostgreSQL connection string, or install pymysql."
                )

            raise ValueError(
                f"Unsupported database scheme '{scheme}'. Supported types: SQLite (sqlite:///) and PostgreSQL (postgresql://)."
            )

        # 2. Path-based SQLite adapter
        if db_path:
            return SQLiteAdapter(db_path=Path(db_path))

        # 3. Explicit type fallback
        if db_type == "postgres":
            raise ValueError("A valid PostgreSQL connection string (postgresql://user:pass@host:5432/db) must be provided.")

        raise ValueError("Must provide either a valid db_path or connection_string to initialize database adapter.")

    @classmethod
    def register_adapter(cls, session_id: str, adapter: BaseDatabaseAdapter) -> None:
        """Register an initialized adapter for a session ID."""
        _SESSION_ADAPTERS[session_id] = adapter

    @classmethod
    def remove_adapter(cls, session_id: str) -> None:
        """Remove and disconnect the active adapter for a session."""
        adapter = _SESSION_ADAPTERS.pop(session_id, None)
        if adapter:
            try:
                adapter.disconnect()
            except Exception:
                pass

    @classmethod
    def get_adapter(cls, session_id: str) -> Optional[BaseDatabaseAdapter]:
        """Retrieve the active adapter for a session, restoring from session store if needed."""
        adapter = _SESSION_ADAPTERS.get(session_id)
        if adapter:
            return adapter

        # Attempt to restore adapter from in-memory session metadata
        from app.services.session_store import get_session
        session = get_session(session_id)
        if not session:
            return None

        db_path = session.get("db_path")
        db_url = session.get("database_url")
        db_type = session.get("db_type", "demo")

        try:
            if db_path and Path(db_path).exists():
                new_adapter = SQLiteAdapter(db_path=Path(db_path))
                cls.register_adapter(session_id, new_adapter)
                return new_adapter

            if db_url:
                new_adapter = cls.create_adapter(db_type=db_type, connection_string=db_url)
                cls.register_adapter(session_id, new_adapter)
                return new_adapter
        except Exception as exc:
            logger.warning("Could not restore database adapter for session %s: %s", session_id, exc)

        return None

    @classmethod
    def unregister_adapter(cls, session_id: str) -> None:
        """Dispose and remove adapter for a session."""
        adapter = _SESSION_ADAPTERS.pop(session_id, None)
        if adapter:
            try:
                adapter.disconnect()
            except Exception:
                pass

    @classmethod
    def clear_all(cls) -> None:
        """Clear all registered adapters."""
        for adapter in _SESSION_ADAPTERS.values():
            try:
                adapter.disconnect()
            except Exception:
                pass
        _SESSION_ADAPTERS.clear()
