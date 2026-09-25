import json
import logging
import time
import uuid
from collections import defaultdict
from datetime import datetime
from typing import List, Dict, Any, Optional, Union
import google.generativeai as genai
from fastapi import APIRouter, HTTPException, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.models.meta_db import ConversationModel, QueryHistoryModel, get_db_session
from app.services.sql_generator import generate_sql, regenerate_sql
from app.services.sql_validator import validate_sql
from app.services.execution_engine import run_select
from app.services.session_store import get_session

logger = logging.getLogger(__name__)

router = APIRouter()

# In-memory sliding window rate limiter: session_id -> list of float timestamps
_QUERY_TIMESTAMPS: Dict[str, List[float]] = defaultdict(list)
RATE_LIMIT_PER_MINUTE = 20
WINDOW_SECONDS = 60.0


def generate_conversation_title(question: str) -> str:
    """Generate a short 3-5 word title summarizing the user question with fast fallback."""
    def _fallback_title(text: str) -> str:
        words = text.strip().split()
        title = " ".join(words[:5]).capitalize()
        return title[:40]

    try:
        model = genai.GenerativeModel("gemini-3.5-flash-lite")
        prompt = (
            f"Generate a short 3-5 word title summarizing this database question: \"{question}\".\n"
            "Return ONLY the plain title text (no quotes, no markdown, max 5 words)."
        )
        res = model.generate_content(prompt, generation_config={"temperature": 0.2, "max_output_tokens": 20})
        title = (res.text or "").strip().strip('"\'')
        if title and len(title) <= 50:
            return title
    except Exception as e:
        logger.warning("Gemini title generation failed (%s). Using fallback title.", e)

    return _fallback_title(question)


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
    conversation_id: Optional[str] = Field(None, description="UUID of the active conversation")
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
    interpreted_text: Optional[str] = None
    detected_language: Optional[str] = None
    self_corrected: bool = False
    correction_attempts: int = 0
    data_available: bool = True
    unavailable_message: Optional[str] = None
    corrected_terms: List[Dict[str, str]] = []



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

    # Ensure conversation exists; if omitted or not found, auto-create under this session
    target_conv_id = payload.conversation_id
    if target_conv_id:
        conv = db.query(ConversationModel).filter(ConversationModel.id == target_conv_id).first()
        if not conv:
            conv = ConversationModel(
                id=target_conv_id,
                session_id=payload.session_id,
                title="New Chat",
                created_at=datetime.utcnow(),
            )
            db.add(conv)
            db.commit()
            db.refresh(conv)
    else:
        conv = ConversationModel(
            id=str(uuid.uuid4()),
            session_id=payload.session_id,
            title="New Chat",
            created_at=datetime.utcnow(),
        )
        db.add(conv)
        db.commit()
        db.refresh(conv)

    # Auto-generate title from the first question if currently default "New Chat"
    if conv.title in ("New Chat", "", None):
        try:
            conv.title = generate_conversation_title(payload.text)
            db.commit()
        except Exception as title_err:
            logger.warning("Could not auto-generate conversation title: %s", title_err)

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

    interpreted_text = gen_data.get("interpreted_text") or payload.text
    detected_lang = gen_data.get("detected_language")
    data_available = bool(gen_data.get("data_available", True))
    unavailable_msg = gen_data.get("unavailable_message")
    corrected_terms = gen_data.get("corrected_terms") or []

    # Handle data unavailable in connected database schema
    if not data_available:
        msg_text = unavailable_msg or "This information is not tracked in the connected database schema."
        query_record = QueryHistoryModel(
            session_id=payload.session_id,
            conversation_id=conv.id,
            nl_query=payload.text,
            generated_sql="-- Data unavailable in schema",
            explanation=msg_text,
            result_json="[]",
            chart_type="none",
            confidence=0.85,
            query_type="unavailable",
            self_corrected=0,
            correction_attempts=0,
            created_at=datetime.utcnow(),
        )
        db.add(query_record)
        db.commit()
        db.refresh(query_record)

        return QueryResponse(
            query_id=str(query_record.id),
            sql=None,
            explanation=msg_text,
            confidence=0.85,
            needs_clarification=False,
            clarification_question=None,
            query_type="unavailable",
            result=[],
            chart_type="none",
            interpreted_text=interpreted_text,
            detected_language=detected_lang,
            self_corrected=False,
            correction_attempts=0,
            data_available=False,
            unavailable_message=msg_text,
            corrected_terms=corrected_terms,
        )

    # Handle clarification needed before validation or execution
    if gen_data.get("needs_clarification", False):
        clarification_q = gen_data.get("clarification_question") or "Could you please clarify your request?"
        confidence = float(gen_data.get("confidence", 0.3))

        query_record = QueryHistoryModel(
            session_id=payload.session_id,
            conversation_id=conv.id,
            nl_query=payload.text,
            generated_sql="-- Needs clarification: " + clarification_q,
            explanation=clarification_q,
            result_json="[]",
            chart_type="none",
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
            interpreted_text=interpreted_text,
            detected_language=detected_lang,
            data_available=True,
            unavailable_message=None,
            corrected_terms=corrected_terms,
        )


    current_sql = gen_data.get("sql", "")
    current_explanation = gen_data.get("explanation", "")
    current_confidence = float(gen_data.get("confidence", 0.9))

    # Self-Correction Retry Loop: up to 2 retries (original attempt + 2 retries = 3 attempts max)
    MAX_RETRIES = 2
    attempt = 0
    corrections_history: List[Dict[str, Any]] = []
    self_corrected = False
    validation: Optional[Dict[str, Any]] = None
    exec_result: Any = None
    friendly_message: str = ""

    while attempt <= MAX_RETRIES:
        # Step A: Validate SQL syntax and safety via sqlglot
        validation = validate_sql(current_sql)
        if not validation.get("valid", False):
            error_msg = validation.get("message", "Invalid SQL syntax.")
            logger.warning(
                "[Self-Correction] Attempt %d: SQL validation failed for session '%s'. SQL: '%s' | Error: '%s'",
                attempt + 1,
                payload.session_id,
                current_sql,
                error_msg,
            )
            if attempt < MAX_RETRIES:
                attempt += 1
                try:
                    regen_data = regenerate_sql(
                        session_id=payload.session_id,
                        original_question=payload.text,
                        failed_sql=current_sql,
                        error_message=error_msg,
                    )
                    new_sql = regen_data.get("sql", "")
                    logger.info(
                        "[Self-Correction] Retry %d generated corrected SQL: '%s'",
                        attempt,
                        new_sql,
                    )
                    corrections_history.append({
                        "attempt": attempt,
                        "failed_sql": current_sql,
                        "error": error_msg,
                        "corrected_sql": new_sql,
                    })
                    current_sql = new_sql
                    current_explanation = regen_data.get("explanation", current_explanation)
                    current_confidence = float(regen_data.get("confidence", 0.85))
                    self_corrected = True
                    continue
                except Exception as r_exc:
                    logger.error("[Self-Correction] regenerate_sql call failed: %s", r_exc)
                    friendly_message = error_msg
                    break
            else:
                friendly_message = error_msg
                break

        # Step B: Execute SQL against SQLite database
        exec_result = run_select(payload.session_id, current_sql)
        if isinstance(exec_result, dict) and "error" in exec_result:
            error_msg = f"Database query execution failed: {exec_result['error']}"
            logger.warning(
                "[Self-Correction] Attempt %d: Database execution failed for session '%s'. SQL: '%s' | Error: '%s'",
                attempt + 1,
                payload.session_id,
                current_sql,
                error_msg,
            )
            if attempt < MAX_RETRIES:
                attempt += 1
                try:
                    regen_data = regenerate_sql(
                        session_id=payload.session_id,
                        original_question=payload.text,
                        failed_sql=current_sql,
                        error_message=error_msg,
                    )
                    new_sql = regen_data.get("sql", "")
                    logger.info(
                        "[Self-Correction] Retry %d generated corrected SQL: '%s'",
                        attempt,
                        new_sql,
                    )
                    corrections_history.append({
                        "attempt": attempt,
                        "failed_sql": current_sql,
                        "error": error_msg,
                        "corrected_sql": new_sql,
                    })
                    current_sql = new_sql
                    current_explanation = regen_data.get("explanation", current_explanation)
                    current_confidence = float(regen_data.get("confidence", 0.85))
                    self_corrected = True
                    continue
                except Exception as r_exc:
                    logger.error("[Self-Correction] regenerate_sql call failed: %s", r_exc)
                    friendly_message = error_msg
                    break
            else:
                friendly_message = error_msg
                break

        # Both validation and execution succeeded!
        break

    # Determine whether the final query succeeded or failed
    is_failed = (
        (validation is not None and not validation.get("valid", False))
        or (isinstance(exec_result, dict) and "error" in exec_result)
    )

    if is_failed:
        # Exhausted all retries without success: record failed query and return friendly error
        query_record = QueryHistoryModel(
            session_id=payload.session_id,
            conversation_id=conv.id,
            nl_query=payload.text,
            generated_sql=current_sql,
            explanation=friendly_message,
            result_json="[]",
            chart_type="none",
            confidence=0.0,
            query_type="select",
            self_corrected=0,
            correction_attempts=attempt,
            corrections_json=json.dumps(corrections_history) if corrections_history else None,
            created_at=datetime.utcnow(),
        )
        db.add(query_record)
        db.commit()
        db.refresh(query_record)

        return QueryResponse(
            query_id=str(query_record.id),
            sql=current_sql,
            explanation=friendly_message,
            confidence=0.0,
            needs_clarification=False,
            clarification_question=None,
            query_type="select",
            result=[],
            chart_type="none",
            interpreted_text=interpreted_text,
            detected_language=detected_lang,
            self_corrected=False,
            correction_attempts=attempt,
            data_available=True,
            unavailable_message=None,
            corrected_terms=corrected_terms,
        )

    # Success (either on first attempt or after self-correction)
    query_record = QueryHistoryModel(
        session_id=payload.session_id,
        conversation_id=conv.id,
        nl_query=payload.text,
        generated_sql=current_sql,
        explanation=current_explanation,
        result_json=json.dumps(exec_result) if exec_result else "[]",
        chart_type="none",
        confidence=current_confidence,
        query_type="select",
        self_corrected=1 if self_corrected else 0,
        correction_attempts=attempt,
        corrections_json=json.dumps(corrections_history) if corrections_history else None,
        created_at=datetime.utcnow(),
    )
    db.add(query_record)
    db.commit()
    db.refresh(query_record)

    return QueryResponse(
        query_id=str(query_record.id),
        sql=current_sql,
        explanation=current_explanation,
        confidence=current_confidence,
        needs_clarification=False,
        clarification_question=None,
        query_type="select",
        result=exec_result or [],
        chart_type="none",
        interpreted_text=interpreted_text,
        detected_language=detected_lang,
        self_corrected=self_corrected,
        correction_attempts=attempt,
        data_available=True,
        unavailable_message=None,
        corrected_terms=corrected_terms,
    )

