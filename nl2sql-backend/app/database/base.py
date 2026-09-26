"""Base database adapter interface for universal database support.

Defines the contract that all concrete database adapters (SQLite, PostgreSQL, MySQL) must implement.
"""

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Union


class BaseDatabaseAdapter(ABC):
    """Abstract base class defining universal database operations."""

    @abstractmethod
    def connect(self) -> None:
        """Establish connection to the target database."""
        pass

    @abstractmethod
    def disconnect(self) -> None:
        """Close active database connection and release resources."""
        pass

    @abstractmethod
    def validate_connection(self) -> bool:
        """Verify database connectivity and responsiveness."""
        pass

    @abstractmethod
    def get_tables(self) -> List[str]:
        """Return list of user table names available in the database."""
        pass

    @abstractmethod
    def get_columns(self, table_name: str) -> List[Dict[str, Any]]:
        """Return column definitions for a table (name, type, nullable, primary_key)."""
        pass

    @abstractmethod
    def get_primary_keys(self, table_name: str) -> List[str]:
        """Return list of primary key column names for a table."""
        pass

    @abstractmethod
    def get_foreign_keys(self, table_name: str) -> List[Dict[str, Any]]:
        """Return foreign key constraints (constrained_columns, referred_table, referred_columns)."""
        pass

    @abstractmethod
    def get_sample_values(self, table_name: str, col_name: str, limit: int = 5) -> List[Any]:
        """Fetch representative distinct sample values for a column."""
        pass

    @abstractmethod
    def get_row_count(self, table_name: str) -> int:
        """Return total row count of a table."""
        pass

    @abstractmethod
    def extract_full_schema(self, sample_limit: int = 5) -> Dict[str, Any]:
        """Extract complete, normalized semantic schema representation including PKs, FKs, and samples."""
        pass

    @abstractmethod
    def execute_query(self, sql: str) -> Union[List[Dict[str, Any]], Dict[str, str]]:
        """Execute a read (SELECT) query and return rows as list of dicts, or error dict."""
        pass

    @abstractmethod
    def execute_write(self, sql: str) -> Dict[str, Any]:
        """Execute a write (INSERT, UPDATE, DELETE) statement in a transaction and return affected row count."""
        pass
