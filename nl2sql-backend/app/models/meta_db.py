import uuid
from datetime import datetime
from sqlalchemy import (
    Column,
    String,
    Integer,
    Float,
    Text,
    DateTime,
    ForeignKey,
    create_engine,
    event,
)
from sqlalchemy.orm import declarative_base, sessionmaker

from app.config import DATABASE_URL, DATA_DIR

# Ensure data directory exists
DATA_DIR.mkdir(parents=True, exist_ok=True)

Base = declarative_base()



class SessionModel(Base):
    __tablename__ = "sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    db_type = Column(String, nullable=False)
    connected_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ConversationModel(Base):
    __tablename__ = "conversations"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    title = Column(String, nullable=False, default="New Chat")
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class QueryHistoryModel(Base):
    __tablename__ = "query_history"

    id = Column(Integer, primary_key=True, autoincrement=True)
    session_id = Column(String, ForeignKey("sessions.id"), nullable=False)
    conversation_id = Column(String, ForeignKey("conversations.id"), nullable=True)
    nl_query = Column(Text, nullable=False)
    generated_sql = Column(Text, nullable=False)
    explanation = Column(Text, nullable=True)
    result_json = Column(Text, nullable=True)
    chart_type = Column(String, nullable=True, default="none")
    confidence = Column(Float, nullable=True)
    query_type = Column(String, nullable=True)
    self_corrected = Column(Integer, default=0, nullable=True)
    correction_attempts = Column(Integer, default=0, nullable=True)
    corrections_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False, "timeout": 15},
)


@event.listens_for(engine, "connect")
def set_sqlite_pragma(dbapi_connection, connection_record):
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.execute("PRAGMA synchronous=NORMAL")
    cursor.close()


SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)



def init_db() -> None:
    """Create all metadata database tables if they do not exist, and perform additive migrations."""
    Base.metadata.create_all(bind=engine)

    # Perform lightweight schema migration for existing SQLite databases
    with engine.begin() as conn:
        # Check conversations table
        raw_conn = conn.connection
        cur = raw_conn.cursor()
        conv_info = cur.execute("PRAGMA table_info(conversations)").fetchall()
        conv_cols = [row[1] for row in conv_info]
        id_type = next((row[2] for row in conv_info if row[1] == "id"), None)

        # If conversations was created with integer id or missing title, recreate it
        if conv_info and (id_type == "INTEGER" or "title" not in conv_cols):
            cur.execute("DROP TABLE IF EXISTS conversations")
            cur.execute("""
                CREATE TABLE conversations (
                    id VARCHAR PRIMARY KEY,
                    session_id VARCHAR NOT NULL REFERENCES sessions(id),
                    title VARCHAR NOT NULL DEFAULT 'New Chat',
                    created_at DATETIME NOT NULL
                )
            """)

        # Check query_history table
        qh_info = cur.execute("PRAGMA table_info(query_history)").fetchall()
        qh_cols = [row[1] for row in qh_info]
        if "conversation_id" not in qh_cols:
            cur.execute("ALTER TABLE query_history ADD COLUMN conversation_id VARCHAR REFERENCES conversations(id)")
        if "explanation" not in qh_cols:
            cur.execute("ALTER TABLE query_history ADD COLUMN explanation TEXT")
        if "result_json" not in qh_cols:
            cur.execute("ALTER TABLE query_history ADD COLUMN result_json TEXT")
        if "chart_type" not in qh_cols:
            cur.execute("ALTER TABLE query_history ADD COLUMN chart_type VARCHAR DEFAULT 'none'")
        if "self_corrected" not in qh_cols:
            cur.execute("ALTER TABLE query_history ADD COLUMN self_corrected INTEGER DEFAULT 0")
        if "correction_attempts" not in qh_cols:
            cur.execute("ALTER TABLE query_history ADD COLUMN correction_attempts INTEGER DEFAULT 0")
        if "corrections_json" not in qh_cols:
            cur.execute("ALTER TABLE query_history ADD COLUMN corrections_json TEXT")
        cur.close()


def get_db_session():
    """Dependency helper to get a database session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
