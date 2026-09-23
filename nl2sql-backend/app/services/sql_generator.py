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
    """Generate SQL from natural language question using Gemini with model fallback.
    
    Returns:
        dict: {"sql": str, "explanation": str, "confidence": float}
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

    base_prompt = f"""You are an expert SQLite SQL engineer.
Given the following SQLite database schema:
{schema_str}

User Question: "{nl_question}"

Instructions:
1. Generate a valid, executable SQLite query that accurately answers the user's question. If the user asks to delete, insert, or update data, generate that query directly.
2. Return ONLY a single valid JSON object. Do not include markdown code fences (```json or ```), backticks, or any introductory or concluding text.
3. Pay close attention to the sample values provided for each column. When filtering on text/categorical columns (such as '1st year', '2nd year'), match the exact text format shown in the sample values rather than assuming numeric values.
4. The JSON object must strictly have this exact structure:
{{
  "sql": "SQL query here",
  "explanation": "Brief explanation of why this query answers the question",
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
1. Pay close attention to the sample values provided for each column and match exact text formats.
2. CRITICAL: Output ONLY raw valid JSON without any markdown formatting, backticks, or extra text.
Format:
{{
  "sql": "SQL query here",
  "explanation": "Explanation here",
  "confidence": 0.9
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
    if "sql" not in data or not isinstance(data["sql"], str):
        raise ValueError("JSON must include 'sql' string")
    if "explanation" not in data or not isinstance(data["explanation"], str):
        raise ValueError("JSON must include 'explanation' string")
    if "confidence" not in data:
        data["confidence"] = 0.8
    else:
        try:
            data["confidence"] = float(data["confidence"])
        except (ValueError, TypeError):
            data["confidence"] = 0.8
