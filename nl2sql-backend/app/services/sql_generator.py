import json
import re
import warnings
from typing import Dict, Any, Optional
from app.config import GEMINI_API_KEY
from app.services.session_store import get_session

warnings.filterwarnings("ignore", category=FutureWarning)

import google.generativeai as genai

import logging

logger = logging.getLogger(__name__)

# Configure Gemini client
genai.configure(api_key=GEMINI_API_KEY, transport="rest")

# Prioritized list of active Gemini models (fastest first)
MODELS_TO_TRY = [
    "gemini-3.5-flash-lite",
    "gemini-3.5-flash",
    "gemini-3.1-flash-lite",
]

# Sticky working model pointer to avoid fallback delays on every call
_WORKING_MODEL: str = "gemini-3.5-flash-lite"

# In-memory query response cache: cache_key -> {"sql": ..., "explanation": ..., "confidence": ...}
_QUERY_CACHE: Dict[str, Dict[str, Any]] = {}


def clear_query_cache(session_id: Optional[str] = None) -> None:
    """Clear query cache for a specific session or globally."""
    if session_id:
        keys_to_del = [k for k in _QUERY_CACHE if k.startswith(f"{session_id}:")]
        for k in keys_to_del:
            _QUERY_CACHE.pop(k, None)
    else:
        _QUERY_CACHE.clear()


def _clean_json_string(text: str) -> str:
    """Strip markdown fences and whitespace from model output."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        # Match ```json ... ``` or ``` ... ```
        pattern = r"^```(?:json)?\s*(.*?)\s*```$"
        match = re.search(pattern, cleaned, re.DOTALL | re.IGNORECASE)
        if match:
            cleaned = match.group(1).strip()
        else:
            lines = cleaned.splitlines()
            if lines[0].startswith("```"):
                lines = lines[1:]
            if lines and lines[-1].startswith("```"):
                lines = lines[:-1]
            cleaned = "\n".join(lines).strip()
    return cleaned


def _format_schema_for_prompt(schema: Dict[str, Any], sample_values_map: Optional[Dict[str, Any]] = None) -> str:
    """Format schema dictionary into readable text for the prompt, including sample values."""
    schema_lines = []
    for table, cols in schema.items():
        col_strs = []
        for c in cols:
            col_name = c.get("name", "")
            col_type = c.get("type", "")
            samples = c.get("sample_values")
            if not samples and sample_values_map and table in sample_values_map:
                samples = sample_values_map[table].get(col_name)
            samples = samples or []
            if samples:
                samples_str = ", ".join(repr(s) if isinstance(s, str) else str(s) for s in samples)
                if col_type:
                    col_strs.append(f"{col_name} ({col_type}, sample values: {samples_str})")
                else:
                    col_strs.append(f"{col_name} (sample values: {samples_str})")
            else:
                if col_type:
                    col_strs.append(f"{col_name} ({col_type})")
                else:
                    col_strs.append(col_name)
        schema_lines.append(f"Table '{table}': {', '.join(col_strs)}")
    return "\n".join(schema_lines)


def generate_sql(session_id: str, nl_question: str) -> Dict[str, Any]:
    """Generate SQL from natural language question using Gemini with clarification and model fallback.
    
    Returns:
        dict: {
            "needs_clarification": bool,
            "clarification_question": Optional[str],
            "sql": Optional[str],
            "explanation": Optional[str],
            "confidence": float
        }
    """
    global _WORKING_MODEL

    cache_key = f"{session_id}:{nl_question.strip().lower()}"
    if cache_key in _QUERY_CACHE:
        logger.info("Serving SQL generation from query cache for: %s", cache_key)
        return dict(_QUERY_CACHE[cache_key])

    session = get_session(session_id)
    if not session:
        raise ValueError(f"Session '{session_id}' not found. Please connect to a database first.")

    schema = session.get("schema", {})
    sample_values_map = session.get("sample_values")
    schema_str = _format_schema_for_prompt(schema, sample_values_map)

    base_prompt = f"""You are an expert SQLite SQL engineer and database analyst.
Given the following SQLite database schema:
{schema_str}

User Question: "{nl_question}"

Instructions:
1. Clarification & Ambiguity Assessment:
   Before generating SQL, decide whether the user's question requires clarification. Set "needs_clarification" to true when:
   - A ranking word is used ("top", "best", "highest", "most", "lowest") without specifying BOTH a metric to rank by AND a number/limit (for example: "give me the top patients" is ambiguous, whereas "top 5 patients by number of appointments" specifies both metric and limit and is NOT ambiguous).
   - A vague qualitative term is used with no defined criteria ("important", "recent", "significant", "good", "bad") without a clear threshold or timeframe (for example: "show me important doctors" is ambiguous).
   - The question could reasonably map to more than one table or column and the correct one cannot be inferred from the schema or sample values.
   Otherwise, if the question has clear criteria or explicit filtering (for example: "list all patients older than 40"), set "needs_clarification" to false.

2. Structure Rules based on "needs_clarification":
   - If "needs_clarification" is true:
     - "needs_clarification": true
     - "clarification_question": a short, specific, polite question asking the user to clarify the ambiguity (e.g., "How would you like to define top patients (e.g. by appointment count or total billing), and how many would you like to see?").
     - "sql": null
     - "explanation": null
     - "confidence": a float below 0.5 (e.g. 0.2 or 0.3)
   - If "needs_clarification" is false:
     - "needs_clarification": false
     - "clarification_question": null
     - "sql": a valid, executable SQLite query that accurately answers the question. If filtering on text/categorical columns (such as '1st year', '2nd year'), match the exact text format shown in the sample values. For top N queries, include appropriate ORDER BY and LIMIT.
     - "explanation": a brief explanation of how the query answers the question.
     - "confidence": a float between 0.7 and 1.0.

3. CRITICAL: Return ONLY a single valid JSON object. Do not include markdown code fences (```json or ```), backticks, or any introductory or concluding text.
Format:
{{
  "needs_clarification": false,
  "clarification_question": null,
  "sql": "SELECT ...",
  "explanation": "Brief explanation...",
  "confidence": 0.95
}}
"""

    gen_config = {
        "temperature": 0.0,
        "max_output_tokens": 800,
    }

    last_error = None

    # Always prioritize the currently confirmed working model first
    models_to_try = [_WORKING_MODEL] + [m for m in MODELS_TO_TRY if m != _WORKING_MODEL]

    for model_name in models_to_try:
        try:
            logger.info("Attempting SQL generation with model: %s", model_name)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(base_prompt, generation_config=gen_config)
            raw_text = response.text or ""
            cleaned = _clean_json_string(raw_text)

            try:
                data = json.loads(cleaned)
                _validate_result(data)
                _WORKING_MODEL = model_name
                _QUERY_CACHE[cache_key] = data
                return data
            except Exception as parse_err:
                logger.warning(
                    "JSON parse error with model %s (%s). Retrying once with strict instructions...",
                    model_name,
                    parse_err,
                )
                retry_prompt = f"""Your previous response was not valid JSON.
Error: {str(parse_err)}
Database Schema:
{schema_str}

User Question: "{nl_question}"

Instructions:
1. Determine if the question needs clarification (e.g. ranking word without metric and limit, or vague terms like 'important' without criteria).
2. If needs_clarification is true, set sql to null, explanation to null, confidence < 0.5, and provide a short clarification_question.
3. If needs_clarification is false, generate valid SQLite in sql, explanation, confidence >= 0.5, and clarification_question to null.
4. Output ONLY raw valid JSON without markdown formatting or backticks:
{{
  "needs_clarification": true or false,
  "clarification_question": "..." or null,
  "sql": "..." or null,
  "explanation": "..." or null,
  "confidence": 0.3 or 0.9
}}
"""
                retry_res = model.generate_content(retry_prompt, generation_config=gen_config)
                retry_cleaned = _clean_json_string(retry_res.text or "")
                retry_data = json.loads(retry_cleaned)
                _validate_result(retry_data)
                _WORKING_MODEL = model_name
                _QUERY_CACHE[cache_key] = retry_data
                return retry_data

        except Exception as exc:
            logger.warning(
                "Model '%s' failed (error: %s: %s). Trying next fallback model...",
                model_name,
                type(exc).__name__,
                exc,
            )
            last_error = exc
            continue

    if last_error:
        raise last_error
    raise RuntimeError("All Gemini model generation attempts failed.")



def _validate_result(data: Any) -> None:
    """Ensure result dictionary contains required fields with expected types."""
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object")

    # Normalize needs_clarification
    needs_clarif = bool(data.get("needs_clarification", False))
    data["needs_clarification"] = needs_clarif

    if needs_clarif:
        clarif_q = data.get("clarification_question")
        if not clarif_q or not isinstance(clarif_q, str) or not clarif_q.strip():
            data["clarification_question"] = "Could you please clarify your request with more specific criteria?"
        else:
            data["clarification_question"] = clarif_q.strip()
        data["sql"] = None
        data["explanation"] = None
        try:
            conf = float(data.get("confidence", 0.3))
            data["confidence"] = min(conf, 0.49)
        except (ValueError, TypeError):
            data["confidence"] = 0.3
    else:
        data["clarification_question"] = None
        sql = data.get("sql")
        if not sql or not isinstance(sql, str) or not sql.strip():
            raise ValueError("JSON must include non-empty 'sql' string when needs_clarification is false")
        data["sql"] = sql.strip()
        explanation = data.get("explanation")
        data["explanation"] = explanation.strip() if isinstance(explanation, str) else ""
        try:
            conf = float(data.get("confidence", 0.9))
            data["confidence"] = max(conf, 0.5)
        except (ValueError, TypeError):
            data["confidence"] = 0.9
