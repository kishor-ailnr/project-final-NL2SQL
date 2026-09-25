import logging
import time
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.meta_db import QueryHistoryModel, get_db_session
from app.services.sql_generator import generate_sql
from app.services.sql_validator import validate_sql
from app.services.execution_engine import run_select
from app.services.session_store import get_session

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory sliding window rate limiter: session_id -> list of float timestamps
_QUERY_TIMESTAMPS: Dict[str, List[float]] = defaultdict(list)
RATE_LIMIT_PER_MINUTE = 20
WINDOW_SECONDS = 60.0


def check_rate_limit(session_id: str) -> None:
    """Enforce in-memory rate limiting of 20 queries per minute per session_id."""
    now = time.time()
    cutoff = now - WINDOW_SECONDS
    timestamps = [t for t in _QUERY_TIMESTAMPS[session_id] if t > cutoff]

    if len(timestamps) >= RATE_LIMIT_PER_MINUTE:
        retry_after = int(WINDOW_SECONDS - (now - timestamps[0])) + 1
        logger.warning(
            "Rate limit exceeded for session_id '%s' (%d requests in 60s). Retry after %ds",
            session_id,
            len(timestamps),
            retry_after,
        )
        raise HTTPException(
            status_code=429,
            detail="Rate limit exceeded. Maximum 20 queries per minute per session. Please wait a moment before trying again.",
            headers={"Retry-After": str(max(1, retry_after))},
        )

    timestamps.append(now)
    _QUERY_TIMESTAMPS[session_id] = timestamps


def reset_rate_limits() -> None:
    """Reset rate limiter state (used for testing)."""
    _QUERY_TIMESTAMPS.clear()


class QueryRequest(BaseModel):
    session_id: str = Field(..., description="ID of the active database session")
    text: str = Field(..., description="Natural language user question")
    language: str = Field("auto", description="Language code, default 'auto'")


class QueryResponse(BaseModel):
    query_id: Union[str, int]
    sql: Optional[str] = None
    explanation: Optional[str] = None
    confidence: float
    needs_clarification: bool = False
    clarification_question: Optional[str] = None
    query_type: str = "select"
    result: List[Any] = []
    chart_type: str = "none"


class HistoryConversation(BaseModel):
    id: str
    nl_query: str
    timestamp: str


class HistoryResponse(BaseModel):
    conversations: List[HistoryConversation]


@router.get("/history", response_model=HistoryResponse)
def get_history(
    session_id: Optional[str] = None,
    db: Session = Depends(get_db_session),
):
    """Retrieve query history from data/meta.db filtered by session_id, most recent first, limit to 20."""
    query = db.query(QueryHistoryModel)
    if session_id:
        query = query.filter(QueryHistoryModel.session_id == session_id)

    records = query.order_by(QueryHistoryModel.created_at.desc()).limit(20).all()

    conversations = [
        HistoryConversation(
            id=str(record.id),
            nl_query=record.nl_query,
            timestamp=record.created_at.strftime("%Y-%m-%d %H:%M:%S") if record.created_at else "",
        )
        for record in records
    ]
    return HistoryResponse(conversations=conversations)


@router.post("/query", response_model=QueryResponse)
def handle_query(
    payload: QueryRequest,
    db: Session = Depends(get_db_session),
):
    """Translate natural language to SQL, validate it, execute it, and record history."""
    # 0. Enforce Rate Limiting (20 queries / min per session_id)
    check_rate_limit(payload.session_id)

    session = get_session(payload.session_id)
    if not session:
        raise HTTPException(
            status_code=404,
            detail="Active session not found. Please connect to a database first.",
        )

    # 1. Generate SQL using Gemini (with clarification detection)
    try:
        gen_data = generate_sql(payload.session_id, payload.text, language=payload.language)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(
            "Error generating SQL for session '%s' and question '%s': %s",
            payload.session_id,
            payload.text,
            exc,
            exc_info=True,
        )
        err_msg = str(exc)
        if "429" in err_msg or "quota" in err_msg.lower() or "toomanyrequests" in type(exc).__name__.lower():
            raise HTTPException(
                status_code=429,
                detail="AI service rate limit or quota exceeded. Please wait a moment and try again.",
            )
        raise HTTPException(
            status_code=500,
            detail="Failed to generate SQL query for this question. Please try rephrasing your question.",
        )

    # Handle clarification needed before validation or execution
    if gen_data.get("needs_clarification", False):
        clarification_q = gen_data.get("clarification_question") or "Could you please clarify your request?"
        confidence = float(gen_data.get("confidence", 0.3))

        query_record = QueryHistoryModel(
            session_id=payload.session_id,
            nl_query=payload.text,
            generated_sql="-- Needs clarification: " + clarification_q,
            confidence=confidence,
            query_type="clarification",
            created_at=datetime.utcnow(),
        )
        db.add(query_record)
        db.commit()
        db.refresh(query_record)

        return QueryResponse(
            query_id=str(query_record.id),
            sql=None,
            explanation=None,
            confidence=confidence,
            needs_clarification=True,
            clarification_question=clarification_q,
            query_type="select",
            result=[],
            chart_type="none",
        )

    sql = gen_data.get("sql", "")
    explanation = gen_data.get("explanation", "")
    confidence = float(gen_data.get("confidence", 0.9))

    # 2. Validate SQL before execution
    validation = validate_sql(sql)
    if not validation.get("valid", False):
        friendly_message = validation.get("message", "Invalid SQL query.")
        query_record = QueryHistoryModel(
            session_id=payload.session_id,
            nl_query=payload.text,
            generated_sql=sql,
            confidence=0.0,
            query_type="select",
            created_at=datetime.utcnow(),
        )
        db.add(query_record)
        db.commit()
        db.refresh(query_record)

        return QueryResponse(
            query_id=str(query_record.id),
            sql=sql,
            explanation=friendly_message,
            confidence=0.0,
            needs_clarification=False,
            clarification_question=None,
            query_type="select",
            result=[],
            chart_type="none",
        )

    # 3. Execute SQL
    exec_result = run_select(payload.session_id, sql)
    if isinstance(exec_result, dict) and "error" in exec_result:
        friendly_message = f"Database query execution failed: {exec_result['error']}"
        query_record = QueryHistoryModel(
            session_id=payload.session_id,
            nl_query=payload.text,
            generated_sql=sql,
            confidence=0.0,
            query_type="select",
            created_at=datetime.utcnow(),
        )
        db.add(query_record)
        db.commit()
        db.refresh(query_record)

        return QueryResponse(
            query_id=str(query_record.id),
            sql=sql,
            explanation=friendly_message,
            confidence=0.0,
            needs_clarification=False,
            clarification_question=None,
            query_type="select",
            result=[],
            chart_type="none",
        )

    # 4. Save successful query to query_history in meta_db
    query_record = QueryHistoryModel(
        session_id=payload.session_id,
        nl_query=payload.text,
        generated_sql=sql,
        confidence=confidence,
        query_type="select",
        created_at=datetime.utcnow(),
    )
    db.add(query_record)
    db.commit()
    db.refresh(query_record)

    return QueryResponse(
        query_id=str(query_record.id),
        sql=sql,
        explanation=explanation,
        confidence=confidence,
        needs_clarification=False,
        clarification_question=None,
        query_type="select",
        result=exec_result,
        chart_type="none",
    )
