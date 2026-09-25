import re
import csv
import io
import sqlite3
import uuid
from typing import Optional
from datetime import datetime
from typing import List, Dict, Any, Literal
from fastapi import APIRouter, HTTPException, Depends, UploadFile, File
from pydantic import BaseModel, Field
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import Session

from app.config import DATA_DIR
from app.models.meta_db import SessionModel, get_db_session
from app.services.session_store import set_session

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

router = APIRouter()


class ConnectDBRequest(BaseModel):
    db_type: str = Field(
        "demo", description="Database type, currently supporting 'demo'"
    )
    demo_name: Optional[str] = Field(
        "hospital", description="Name of the demo database ('hospital' or 'ecommerce')"
    )
    connection_string: Optional[str] = Field(
        None, description="Optional connection string"
    )


class ConnectDBResponse(BaseModel):
    session_id: str
    status: str
    tables: List[str]


class SessionStatusResponse(BaseModel):
    valid: bool
    status: Optional[str] = "connected"
    session_id: Optional[str] = None
    tables: Optional[List[str]] = []


def sanitize_table_name(filename: str) -> str:
    """Sanitize filename to a valid, clean SQLite table name.

    Rules:
    1. Strip the file extension.
    2. Convert to lowercase.
    3. Replace spaces and special characters with underscores.
    4. Ensure it starts with a letter (prefix with 't_' if it would otherwise start with a number or non-letter).
    """
    base = filename.rsplit(".", 1)[0] if "." in filename else filename
    base = base.lower()
    cleaned = re.sub(r"[^a-z0-9_]+", "_", base).strip("_")
    if not cleaned:
        cleaned = "uploaded_data"
    if cleaned[0].isdigit():
        cleaned = f"t_{cleaned}"
    elif not cleaned[0].isalpha():
        cleaned = f"t_{cleaned}"
    return cleaned


def fetch_column_samples(sqlite_conn: sqlite3.Connection, table_name: str, col_name: str, limit: int = 5) -> List[Any]:
    """Fetch 3-5 distinct non-null, non-empty sample values for a column from a SQLite table."""
    try:
        safe_col = col_name.replace('"', '""')
        safe_table = table_name.replace('"', '""')
        query = f'SELECT DISTINCT "{safe_col}" FROM "{safe_table}" WHERE "{safe_col}" IS NOT NULL AND TRIM(CAST("{safe_col}" AS TEXT)) != "" LIMIT {limit};'
        rows = sqlite_conn.execute(query).fetchall()
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


def inspect_db_schema_and_samples(
    db_path: Path,
    sample_limit: int = 5,
) -> tuple[List[str], Dict[str, List[Dict[str, Any]]], Dict[str, Dict[str, List[Any]]]]:
    """Inspect tables, column definitions, and sample values from a SQLite database file."""
    engine = create_engine(
        f"sqlite:///{db_path.as_posix()}",
        connect_args={"check_same_thread": False},
    )
    inspector = inspect(engine)
    table_names = inspector.get_table_names()

    schema_info: Dict[str, List[Dict[str, Any]]] = {}
    sample_values_map: Dict[str, Dict[str, List[Any]]] = {}

    conn = sqlite3.connect(str(db_path))
    try:
        for table in table_names:
            cols = inspector.get_columns(table)
            sample_values_map[table] = {}
            col_list = []
            for col in cols:
                col_name = col["name"]
                col_type = str(col["type"])
                samples = fetch_column_samples(conn, table, col_name, limit=sample_limit)
                sample_values_map[table][col_name] = samples
                col_list.append({
                    "name": col_name,
                    "type": col_type,
                    "sample_values": samples,
                })
            schema_info[table] = col_list
    finally:
        conn.close()

    return table_names, schema_info, sample_values_map


_DEMO_SCHEMA_CACHE: Dict[str, Dict[str, Any]] = {}


def get_demo_schema(demo_name: str) -> Optional[Dict[str, Any]]:
    """Retrieve demo database schema from in-memory cache, or load and cache it."""
    if demo_name in _DEMO_SCHEMA_CACHE:
        return _DEMO_SCHEMA_CACHE[demo_name]

    db_filename = f"demo_{demo_name}.db"
    db_path = DATA_DIR / db_filename
    if not db_path.exists():
        return None

    table_names, schema_info, sample_values_map = inspect_db_schema_and_samples(db_path)

    demo_data = {
        "tables": table_names,
        "schema": schema_info,
        "sample_values": sample_values_map,
        "db_path": db_path,
        "database_url": f"sqlite:///{db_path.as_posix()}",
    }
    _DEMO_SCHEMA_CACHE[demo_name] = demo_data
    return demo_data


def preload_demo_cache() -> None:
    """Pre-warm schema cache for all available demo databases."""
    for demo_name in ["hospital", "ecommerce"]:
        try:
            get_demo_schema(demo_name)
        except Exception:
            pass


@router.post("/connect-db", response_model=ConnectDBResponse)
def connect_database(
    payload: ConnectDBRequest,
    db: Session = Depends(get_db_session),
):
    """Connect to a demo SQLite database, extract its schema, and initialize a session."""
    demo_name = payload.demo_name or "hospital"
    if demo_name not in ["hospital", "ecommerce"]:
        demo_name = "hospital"

    cached_demo = get_demo_schema(demo_name)
    if not cached_demo:
        logger.error("Demo database '%s' not found on disk at DATA_DIR", demo_name)
        raise HTTPException(
            status_code=404,
            detail=f"Database for '{demo_name}' is currently unavailable. Please ensure it is seeded.",
        )

    table_names = cached_demo["tables"]
    schema_info = cached_demo["schema"]
    db_path = cached_demo["db_path"]
    database_url = cached_demo["database_url"]

    # Generate session ID and register in meta database
    session_id = str(uuid.uuid4())
    session_record = SessionModel(
        id=session_id,
        db_type=f"demo_{demo_name}",
        connected_at=datetime.utcnow(),
    )
    db.add(session_record)
    db.commit()

    # Store in memory session store
    set_session(
        session_id,
        {
            "db_type": payload.db_type,
            "demo_name": demo_name,
            "db_path": db_path,
            "database_url": database_url,
            "tables": table_names,
            "schema": schema_info,
            "sample_values": cached_demo.get("sample_values", {}),
        },
    )

    return ConnectDBResponse(
        session_id=session_id,
        status="connected",
        tables=table_names,
    )


@router.get("/session-status", response_model=SessionStatusResponse)
def get_session_status(session_id: str):
    """Verify if a session is currently active or restorable from database."""
    from app.services.session_store import get_session
    session = get_session(session_id)
    if not session:
        return SessionStatusResponse(
            valid=False,
            status="expired",
            session_id=session_id,
            tables=[],
        )
    return SessionStatusResponse(
        valid=True,
        status="connected",
        session_id=session_id,
        tables=session.get("tables", []),
    )



@router.post("/upload-db", response_model=ConnectDBResponse)
async def upload_database(
    file: UploadFile = File(...),
    db: Session = Depends(get_db_session),
):
    """Upload a .csv or .sql file, import into a new session SQLite database, and return session."""
    filename = file.filename or "uploaded_data"
    lower_name = filename.lower()
    if not (lower_name.endswith(".csv") or lower_name.endswith(".sql")):
        raise HTTPException(
            status_code=400,
            detail="Unsupported file format. Please upload a .csv or .sql file.",
        )

    session_id = str(uuid.uuid4())
    db_filename = f"upload_{session_id}.db"
    db_path = DATA_DIR / db_filename

    content_bytes = await file.read()
    if not content_bytes or len(content_bytes.strip()) == 0:
        raise HTTPException(
            status_code=400,
            detail="The uploaded file is empty.",
        )

    try:
        sqlite_conn = sqlite3.connect(str(db_path))
        cursor = sqlite_conn.cursor()

        if lower_name.endswith(".sql"):
            # Execute SQL script
            try:
                sql_text = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                sql_text = content_bytes.decode("latin-1")
            cursor.executescript(sql_text)
            sqlite_conn.commit()

        elif lower_name.endswith(".csv"):
            # Import CSV into SQLite table
            try:
                csv_text = content_bytes.decode("utf-8")
            except UnicodeDecodeError:
                csv_text = content_bytes.decode("latin-1")

            csv_file = io.StringIO(csv_text)
            reader = csv.reader(csv_file)
            headers = next(reader, None)
            if not headers:
                sqlite_conn.close()
                if db_path.exists():
                    db_path.unlink()
                raise HTTPException(
                    status_code=400,
                    detail="This file couldn't be read as a valid CSV/SQLite file (missing header row).",
                )

            # Sanitize table name
            table_name = sanitize_table_name(filename)

            # Sanitize column names
            clean_headers = []
            for i, h in enumerate(headers):
                c_name = re.sub(r"[^a-zA-Z0-9_]", "_", h.strip()).strip("_")
                clean_headers.append(c_name if c_name else f"col_{i+1}")

            col_defs = ", ".join([f'"{col}" TEXT' for col in clean_headers])
            cursor.execute(f'CREATE TABLE "{table_name}" ({col_defs});')

            placeholders = ", ".join(["?"] * len(clean_headers))
            insert_sql = f'INSERT INTO "{table_name}" VALUES ({placeholders});'

            rows_to_insert = []
            for row in reader:
                if len(row) < len(clean_headers):
                    row.extend([""] * (len(clean_headers) - len(row)))
                elif len(row) > len(clean_headers):
                    row = row[: len(clean_headers)]
                rows_to_insert.append(row)

            if rows_to_insert:
                cursor.executemany(insert_sql, rows_to_insert)
            sqlite_conn.commit()

        sqlite_conn.close()

    except HTTPException:
        raise
    except Exception as exc:
        if db_path.exists():
            try:
                db_path.unlink()
            except Exception:
                pass
        logger.error("Failed to parse uploaded file '%s': %s", filename, exc, exc_info=True)
        raise HTTPException(
            status_code=400,
            detail="This file could not be read as a valid CSV or SQLite file. Please check file format and encoding.",
        )

    # Inspect schema with SQLAlchemy and extract sample values
    table_names, schema_info, sample_values_map = inspect_db_schema_and_samples(db_path)

    if not table_names:
        if db_path.exists():
            db_path.unlink()
        raise HTTPException(
            status_code=400,
            detail="This file couldn't be read as a valid CSV/SQLite file (no tables found).",
        )

    # Save session record in meta database
    session_record = SessionModel(
        id=session_id,
        db_type=f"upload_{session_id}",
        connected_at=datetime.utcnow(),
    )
    db.add(session_record)
    db.commit()

    # Store in memory session store
    set_session(
        session_id,
        {
            "db_type": "upload",
            "upload_name": filename,
            "db_path": db_path,
            "database_url": f"sqlite:///{db_path.as_posix()}",
            "tables": table_names,
            "schema": schema_info,
            "sample_values": sample_values_map,
        },
    )

    return ConnectDBResponse(
        session_id=session_id,
        status="connected",
        tables=table_names,
    )

