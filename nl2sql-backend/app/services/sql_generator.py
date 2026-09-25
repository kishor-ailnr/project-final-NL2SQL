import difflib
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


def detect_input_language(text: str) -> str:
    """Detect whether user query is written in Tamil script, Thanglish, or English.
    
    Returns:
        'tamil': if text contains Unicode characters in Tamil block (\u0B80-\u0BFF).
        'thanglish': if text is Latin script containing common Tamil transliteration words/patterns.
        'english': otherwise.
    """
    if any("\u0b80" <= c <= "\u0bff" for c in text):
        return "tamil"

    thanglish_words = {
        "vayasuku", "vayasu", "mela", "keela", "irukra", "irukku", "irukkum",
        "kaatu", "kaatunga", "kudu", "kudunga", "pannu", "pannunga", "yaaru",
        "enna", "ethana", "eppadi", "eppa", "ellam", "ella", "maruthuvar", "noi",
        "noiyali", "noiyaligal", "thara", "solli", "paaru", "mattum", "inga", "enga",
        "oru", "rendu", "aana", "aachu", "romba", "mukkiyam", "mukkiyamaana", "periya",
        "chinna", "adutha", "munnadi", "pinnaadi", "epdi", "yenna", "yethana",
        "thanga", "konjam", "paakanum", "theriyum", "venum", "sollu", "sollunga"
    }
    tokens = set(re.findall(r"\b[a-zA-Z]+\b", text.lower()))
    if tokens.intersection(thanglish_words):
        return "thanglish"

    return "english"


def _enforce_language(data: Dict[str, Any], detected_lang: str, model: Optional[Any] = None) -> None:
    """Enforce language constraints on explanation and clarification_question."""
    data["detected_language"] = detected_lang
    if detected_lang == "thanglish":
        if data.get("explanation"):
            exp = data["explanation"].strip()
            if not (exp.startswith("Understood —") or exp.startswith("Understood -") or exp.startswith("Understood –")):
                data["explanation"] = f"Understood — {exp}"
        if data.get("clarification_question"):
            cq = data["clarification_question"].strip()
            if not (cq.startswith("Understood —") or cq.startswith("Understood -") or cq.startswith("Understood –")):
                data["clarification_question"] = f"Understood — {cq}"
    elif detected_lang == "tamil":
        # If explanation contains NO Tamil Unicode characters, translate to Tamil
        if data.get("explanation") and not any("\u0b80" <= c <= "\u0bff" for c in data["explanation"]):
            logger.warning("Gemini returned non-Tamil explanation for Tamil query; translating to Tamil...")
            if model:
                try:
                    t_resp = model.generate_content(
                        f"Translate this query explanation into natural Tamil script (தமிழ் எழுத்தில்). Return ONLY the Tamil translation without quotes or English:\n\n{data['explanation']}"
                    )
                    if t_resp.text and any("\u0b80" <= c <= "\u0bff" for c in t_resp.text):
                        data["explanation"] = t_resp.text.strip()
                except Exception as te:
                    logger.warning("Tamil translation fallback failed: %s", te)
            if not any("\u0b80" <= c <= "\u0bff" for c in (data.get("explanation") or "")):
                data["explanation"] = "இந்த வினவல் கொடுக்கப்பட்ட நிபந்தனையின் அடிப்படையில் தொடர்புடைய தரவை மீட்டெடுக்கிறது."

        # If clarification_question contains NO Tamil Unicode characters, translate to Tamil
        if data.get("clarification_question") and not any("\u0b80" <= c <= "\u0bff" for c in data["clarification_question"]):
            logger.warning("Gemini returned non-Tamil clarification_question for Tamil query; translating to Tamil...")
            if model:
                try:
                    t_resp = model.generate_content(
                        f"Translate this clarification question into natural Tamil script (தமிழ் எழுத்தில்). Return ONLY the Tamil translation without quotes or English:\n\n{data['clarification_question']}"
                    )
                    if t_resp.text and any("\u0b80" <= c <= "\u0bff" for c in t_resp.text):
                        data["clarification_question"] = t_resp.text.strip()
                except Exception as te:
                    logger.warning("Tamil clarification translation fallback failed: %s", te)
            if not any("\u0b80" <= c <= "\u0bff" for c in (data.get("clarification_question") or "")):
                data["clarification_question"] = "தயவுசெய்து உங்கள் கேள்வியை மேலும் தெளிவுபடுத்தவும்."


def generate_sql(session_id: str, nl_question: str, language: str = "auto") -> Dict[str, Any]:
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

    # Schema-aware retrieval (RAG): retrieve top 3-4 most relevant tables (or all if <= 4)
    from app.services.rag_service import retrieve_relevant_tables
    relevant_tables = retrieve_relevant_tables(session_id, nl_question, top_k=4)

    if relevant_tables and len(relevant_tables) < len(schema):
        logger.info(
            "RAG filtered schema for session '%s' from %d tables to %d relevant tables: %s",
            session_id,
            len(schema),
            len(relevant_tables),
            relevant_tables,
        )
        filtered_schema = {tbl: cols for tbl, cols in schema.items() if tbl in relevant_tables}
        filtered_sample_values = (
            {tbl: vals for tbl, vals in (sample_values_map or {}).items() if tbl in relevant_tables}
            if sample_values_map
            else None
        )
    else:
        filtered_schema = schema
        filtered_sample_values = sample_values_map

    schema_str = _format_schema_for_prompt(filtered_schema, filtered_sample_values)

    detected_lang = detect_input_language(nl_question)
    logger.info("Detected query language for '%s': %s", nl_question, detected_lang)

    if detected_lang == "tamil":
        lang_instruction = """The user's question is in: TAMIL SCRIPT. You MUST write the 'explanation' field and 'clarification_question' field (if used) in Tamil script (தமிழ் எழுத்தில்). Do NOT respond in English. This is a strict requirement, not optional."""
    elif detected_lang == "thanglish":
        lang_instruction = """The user's question is in: THANGLISH (Tamil words in Latin script). You MUST write the 'explanation' field in simple, clear English (since generating Thanglish output reliably is not feasible) — but explicitly acknowledge in one short clause that you understood a Thanglish/Tamil question, e.g. start with 'Understood — ' followed by the English explanation."""
    else:
        lang_instruction = """The user's question is in: ENGLISH. Respond in English as normal."""

    self_check_instruction = """Before finalizing your response, verify: does the 'explanation' field match the required language above? If not, rewrite it in the correct language before responding."""

    base_prompt = f"""You are an expert SQLite SQL engineer and database analyst.
Given the following SQLite database schema:
{schema_str}

Instructions:
1. Speech-to-Text Correction & Interpreted Text:
   - The user's input may come from speech recognition, which occasionally mishears words (for example: unusual word combinations, typos, or phonetically similar words like "shom me pashents older then fourty").
   - Always return an "interpreted_text" field in the JSON response:
     - If the input text looks like it could contain speech-recognition errors or typos, infer the most likely intended sentence and put that corrected version in "interpreted_text", in the same language/script as the input (for example: "shom me pashents older then fourty" -> "show me patients older than forty").
     - If the input already looks clean and normal (e.g. clearly typed text), "interpreted_text" should just be the same as the input.
   - Base your SQL generation and query interpretation on this corrected "interpreted_text".

2. Language & Dialect Understanding (English, Tamil, and Thanglish):
   - Understand the intent accurately whether the user writes in English, Tamil script, or Thanglish (Tamil words written in Latin/English script).
   - Thanglish calibrations:
     - "40 vayasuku mela patients kaatu" or "40 vayasuku mela irukra patients ellam kaatu" means "show/list patients older than 40" (filter: WHERE age > 40 on patients table).
     - "doctor ellam list pannu" or "doctor list kudu" means "list all doctors" (SELECT * FROM doctors).
     - "top patients yaaru" means "who are the top patients" (ambiguous ranking if metric and limit are not specified).

3. Clarification & Ambiguity Assessment:
   Before generating SQL, decide whether the interpreted question requires clarification. Set "needs_clarification" to true when:
   - A ranking word is used ("top", "best", "highest", "most", "lowest", "yaaru top", "சிறந்த", etc.) without specifying BOTH a metric to rank by AND a number/limit (for example: "give me the top patients", "top patients yaaru", or "சிறந்த மருத்துவர்களை காட்டு" is ambiguous, whereas "top 5 patients by number of appointments" specifies both metric and limit and is NOT ambiguous).
   - A vague qualitative term is used with no defined criteria ("important", "recent", "significant", "good", "bad", "mukkiyamaana", "முக்கியமான") without a clear threshold or timeframe.
   - The question could reasonably map to more than one table or column and the correct one cannot be inferred from the schema or sample values.
   Otherwise, if the question has clear criteria or explicit filtering (for example: "list all patients older than 40", "40 வயதுக்கு மேற்பட்ட நோயாளிகளை காட்டு", or "40 vayasuku mela irukra patients ellam kaatu"), set "needs_clarification" to false.

4. Data Availability Assessment:
   - Check if the question asks for data, metrics, entities, or concepts that do not exist or cannot be derived from the database schema provided above (e.g. asking for stock prices, weather, patient insurance policies, or credit card numbers when no such tables or columns exist).
   - If the requested data is NOT tracked in the schema:
     - Set "data_available": false
     - Set "unavailable_message": a calm, polite message explaining what information is not tracked in the connected database schema (e.g. "This database schema does not track patient insurance details or policies.").
     - Set "sql": null
     - Set "explanation": null
     - Set "needs_clarification": false
     - Set "confidence": 0.85
   - If the requested data IS tracked in the schema:
     - Set "data_available": true
     - Set "unavailable_message": null

5. Corrected Terms Tracking:
   - If you corrected any misspelled or phonetically misheard words between the user's input and "interpreted_text", provide them in "corrected_terms" as a list of {{"original": "misheard_word", "corrected": "fixed_word"}}.
   - Example: [{{"original": "pashents", "corrected": "patients"}}, {{"original": "fourty", "corrected": "forty"}}]
   - If no words were corrected, return [].

6. Output Structure Rules based on "needs_clarification" and "data_available":
   - If "data_available" is false:
     - "data_available": false
     - "unavailable_message": a calm informational message
     - "corrected_terms": [...]
     - "needs_clarification": false
     - "clarification_question": null
     - "interpreted_text": the corrected/cleaned input question
     - "sql": null
     - "explanation": null
     - "confidence": 0.85
   - Else if "needs_clarification" is true:
     - "data_available": true
     - "unavailable_message": null
     - "corrected_terms": [...]
     - "needs_clarification": true
     - "clarification_question": a short, specific, polite question asking the user to clarify the ambiguity (in the required output language).
     - "interpreted_text": the corrected/cleaned version of the input question.
     - "sql": null
     - "explanation": null
     - "confidence": a float below 0.5 (e.g. 0.2 or 0.3)
   - Else:
     - "data_available": true
     - "unavailable_message": null
     - "corrected_terms": [...]
     - "needs_clarification": false
     - "clarification_question": null
     - "interpreted_text": the corrected/cleaned version of the input question.
     - "sql": a valid, executable SQLite query that accurately answers the question based on the interpreted text. If filtering on text/categorical columns, match the exact text format shown in the sample values. For top N queries, include appropriate ORDER BY and LIMIT.
     - "explanation": a concise explanation of how the query answers the question (in the required output language).
     - "confidence": a float between 0.7 and 1.0.

User Question to Answer:
"{nl_question}"

Language Instruction:
{lang_instruction}

Self-Check:
{self_check_instruction}

CRITICAL: Return ONLY a single valid JSON object. Do not include markdown code fences (```json or ```), backticks, or any introductory or concluding text.
Format:
{{
  "data_available": true,
  "unavailable_message": null,
  "corrected_terms": [],
  "needs_clarification": false,
  "clarification_question": null,
  "interpreted_text": "the corrected/cleaned version of the input",
  "sql": "SELECT ...",
  "explanation": "...",
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
                _validate_result(data, nl_question)
                _enforce_language(data, detected_lang, model)
                data["relevant_tables"] = relevant_tables
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

Instructions:
1. Determine if the requested data exists in the schema. If absent, set "data_available": false, provide "unavailable_message", set sql to null.
2. Determine if the question needs clarification (e.g. ranking word without metric and limit, or vague terms like 'important' without criteria).
3. Fix speech-to-text mistakes in interpreted_text and list {{"original", "corrected"}} pairs in corrected_terms.
4. If needs_clarification is true, set sql to null, explanation to null, confidence < 0.5, and provide a short clarification_question.
5. If valid and available, generate valid SQLite in sql, explanation, confidence >= 0.5.

User Question to Answer:
"{nl_question}"

Language Instruction:
{lang_instruction}

Self-Check:
{self_check_instruction}

Output ONLY raw valid JSON without markdown formatting or backticks:
{{
  "data_available": true or false,
  "unavailable_message": "..." or null,
  "corrected_terms": [],
  "needs_clarification": true or false,
  "clarification_question": "..." or null,
  "interpreted_text": "corrected sentence",
  "sql": "..." or null,
  "explanation": "..." or null,
  "confidence": 0.3 or 0.9
}}
"""
                retry_res = model.generate_content(retry_prompt, generation_config=gen_config)
                retry_cleaned = _clean_json_string(retry_res.text or "")
                retry_data = json.loads(retry_cleaned)
                _validate_result(retry_data, nl_question)
                _enforce_language(retry_data, detected_lang, model)
                retry_data["relevant_tables"] = relevant_tables
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



def _extract_word_corrections(original: str, corrected: str) -> list:
    """Extract individual {original, corrected} word pairs between input and interpreted text."""
    if not original or not corrected:
        return []
    orig_words = re.findall(r"\w+|[^\w\s]", original)
    corr_words = re.findall(r"\w+|[^\w\s]", corrected)
    matcher = difflib.SequenceMatcher(None, [w.lower() for w in orig_words], [w.lower() for w in corr_words])
    pairs = []
    for tag, i1, i2, j1, j2 in matcher.get_opcodes():
        if tag == "replace":
            orig_chunk = " ".join(orig_words[i1:i2]).strip()
            corr_chunk = " ".join(corr_words[j1:j2]).strip()
            if orig_chunk.lower() != corr_chunk.lower():
                pairs.append({"original": orig_chunk, "corrected": corr_chunk})
    return pairs


def _validate_result(data: Any, nl_question: str = "") -> None:
    """Ensure result dictionary contains required fields with expected types."""
    if not isinstance(data, dict):
        raise ValueError("Expected JSON object")

    # Normalize interpreted_text
    interpreted = data.get("interpreted_text")
    if not interpreted or not isinstance(interpreted, str) or not interpreted.strip():
        data["interpreted_text"] = nl_question
    else:
        data["interpreted_text"] = interpreted.strip()

    # Normalize data_available & unavailable_message
    data_available = bool(data.get("data_available", True))
    data["data_available"] = data_available
    if not data_available:
        unavail_msg = data.get("unavailable_message")
        if not unavail_msg or not isinstance(unavail_msg, str) or not unavail_msg.strip():
            data["unavailable_message"] = "This information is not tracked in the connected database schema."
        else:
            data["unavailable_message"] = unavail_msg.strip()
        data["sql"] = None
        data["explanation"] = None
        data["needs_clarification"] = False
        data["clarification_question"] = None
        try:
            conf = float(data.get("confidence", 0.85))
            data["confidence"] = conf
        except (ValueError, TypeError):
            data["confidence"] = 0.85
    else:
        data["unavailable_message"] = None

    # Normalize corrected_terms
    corrected_terms = data.get("corrected_terms")
    valid_pairs = []
    if isinstance(corrected_terms, list):
        for item in corrected_terms:
            if isinstance(item, dict) and "original" in item and "corrected" in item:
                orig = str(item["original"]).strip()
                corr = str(item["corrected"]).strip()
                if orig and corr and orig.lower() != corr.lower():
                    valid_pairs.append({"original": orig, "corrected": corr})
    # If model did not output pairs but input was corrected, derive automatically
    if not valid_pairs and data.get("interpreted_text") and nl_question:
        valid_pairs = _extract_word_corrections(nl_question, data["interpreted_text"])
    data["corrected_terms"] = valid_pairs

    if not data_available:
        return

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
            raise ValueError("JSON must include non-empty 'sql' string when needs_clarification is false and data is available")
        data["sql"] = sql.strip()
        explanation = data.get("explanation")
        data["explanation"] = explanation.strip() if isinstance(explanation, str) else ""
        try:
            conf = float(data.get("confidence", 0.9))
            data["confidence"] = max(conf, 0.5)
        except (ValueError, TypeError):
            data["confidence"] = 0.9


def regenerate_sql(
    session_id: str,
    original_question: str,
    failed_sql: str,
    error_message: str,
) -> Dict[str, Any]:
    """Regenerate and fix a failed SQL query using Gemini with explicit failure context.

    Sends the original user question, the failed SQL query, and the exact error message
    (from sqlglot AST validation or SQLite execution) back to Gemini for self-correction.
    """
    global _WORKING_MODEL

    session = get_session(session_id)
    if not session:
        raise ValueError(f"Session '{session_id}' not found. Please connect to a database first.")

    schema = session.get("schema", {})
    sample_values_map = session.get("sample_values")

    # Schema-aware retrieval (RAG)
    from app.services.rag_service import retrieve_relevant_tables
    relevant_tables = retrieve_relevant_tables(session_id, original_question, top_k=4)

    if relevant_tables and len(relevant_tables) < len(schema):
        filtered_schema = {tbl: cols for tbl, cols in schema.items() if tbl in relevant_tables}
        filtered_sample_values = (
            {tbl: vals for tbl, vals in (sample_values_map or {}).items() if tbl in relevant_tables}
            if sample_values_map
            else None
        )
    else:
        filtered_schema = schema
        filtered_sample_values = sample_values_map

    schema_str = _format_schema_for_prompt(filtered_schema, filtered_sample_values)
    detected_lang = detect_input_language(original_question)

    if detected_lang == "tamil":
        lang_instruction = """The user's question is in: TAMIL SCRIPT. You MUST write the 'explanation' field in Tamil script (தமிழ் எழுத்தில்). Do NOT respond in English."""
    elif detected_lang == "thanglish":
        lang_instruction = """The user's question is in: THANGLISH. Write the 'explanation' in English starting with 'Understood — '."""
    else:
        lang_instruction = """The user's question is in: ENGLISH. Respond in English as normal."""

    self_check_instruction = """Before finalizing your response, verify: does the corrected SQL fix the exact error specified, and does the 'explanation' match the required language?"""

    prompt = f"""You are an expert SQLite SQL engineer and database analyst.
A previously generated SQL query failed validation or database execution. Your task is to diagnose the error and provide a corrected, working SQLite query.

Original User Question:
"{original_question}"

Failed SQL Query:
{failed_sql}

Exact Error Message:
{error_message}

Database Schema and Sample Values:
{schema_str}

Instructions:
1. Carefully analyze the Error Message and Failed SQL Query:
   - Check if an invalid column or table name was referenced, and replace it with the exact column/table name from the schema above.
   - Check if there was a syntax error (e.g. missing commas, misplaced keywords, unclosed quotes, invalid aliases) and fix it.
   - Ensure all joins match valid foreign keys or column types.
2. Produce a corrected, fully valid, executable SQLite query that accurately answers the user's question.
3. Provide a clear, concise explanation of the corrected query.
4. Output ONLY a single raw valid JSON object without markdown fences, code blocks, or backticks:
{{
  "needs_clarification": false,
  "clarification_question": null,
  "interpreted_text": "{original_question}",
  "sql": "SELECT ...",
  "explanation": "...",
  "confidence": 0.95
}}

Language Instruction:
{lang_instruction}

Self-Check:
{self_check_instruction}
"""

    gen_config = {
        "temperature": 0.0,
        "max_output_tokens": 800,
    }

    last_error = None
    models_to_try = [_WORKING_MODEL] + [m for m in MODELS_TO_TRY if m != _WORKING_MODEL]

    for model_name in models_to_try:
        try:
            logger.info("Attempting SQL self-correction with model: %s", model_name)
            model = genai.GenerativeModel(model_name)
            response = model.generate_content(prompt, generation_config=gen_config)
            raw_text = response.text or ""
            cleaned = _clean_json_string(raw_text)

            try:
                data = json.loads(cleaned)
                _validate_result(data, original_question)
                _enforce_language(data, detected_lang, model)
                data["relevant_tables"] = relevant_tables
                _WORKING_MODEL = model_name
                return data
            except Exception as parse_err:
                logger.warning(
                    "JSON parse error during self-correction with model %s (%s). Retrying...",
                    model_name,
                    parse_err,
                )
                retry_prompt = f"""Your previous response was not valid JSON.
Error: {str(parse_err)}
Database Schema:
{schema_str}

Output ONLY raw valid JSON:
{{
  "needs_clarification": false,
  "clarification_question": null,
  "interpreted_text": "{original_question}",
  "sql": "SELECT ...",
  "explanation": "...",
  "confidence": 0.9
}}
"""
                retry_res = model.generate_content(retry_prompt, generation_config=gen_config)
                retry_cleaned = _clean_json_string(retry_res.text or "")
                retry_data = json.loads(retry_cleaned)
                _validate_result(retry_data, original_question)
                _enforce_language(retry_data, detected_lang, model)
                retry_data["relevant_tables"] = relevant_tables
                _WORKING_MODEL = model_name
                return retry_data

        except Exception as exc:
            logger.warning(
                "Self-correction model '%s' failed (error: %s: %s). Trying next fallback model...",
                model_name,
                type(exc).__name__,
                exc,
            )
            last_error = exc
            continue

    if last_error:
        raise last_error
    raise RuntimeError("All Gemini model self-correction attempts failed.")

