import copy
import difflib
import hashlib
import json
import logging
import re
import time
import warnings
from typing import Dict, Any, Optional
from app.config import GEMINI_API_KEY
from app.services.session_store import get_session

warnings.filterwarnings("ignore", category=FutureWarning)

import google.generativeai as genai

logger = logging.getLogger(__name__)

# Configure Gemini client if API key is present
if GEMINI_API_KEY:
    genai.configure(api_key=GEMINI_API_KEY, transport="rest")

# Prioritized list of active Gemini models (fastest and available first)
MODELS_TO_TRY = [
    "gemini-3.1-flash-lite",
    "gemini-flash-latest",
    "gemini-3.5-flash-lite",
    "gemini-3.6-flash",
]

# Sticky working model pointer to avoid fallback delays on every call
_WORKING_MODEL: str = "gemini-3.1-flash-lite"

# ---------------------------------------------------------------------------
# In-Memory Response Caching (TTL: 10 minutes)
# Key: SHA-256(schema_signature + normalized_question + language)
# Value: {"response": Dict[str, Any], "created_at": float}
# ---------------------------------------------------------------------------
_QUERY_CACHE: Dict[str, Dict[str, Any]] = {}
CACHE_TTL_SECONDS: float = 600.0  # 10 minutes


def _compute_schema_signature(session: Optional[Dict[str, Any]]) -> str:
    """Compute a deterministic signature of the session's database schema."""
    if not session:
        return "no_session"
    schema = session.get("schema", {})
    tables = session.get("tables", [])
    parts = []
    for tbl in sorted(schema.keys()):
        cols = schema[tbl]
        col_sigs = []
        for c in cols:
            if isinstance(c, dict):
                col_sigs.append(f"{c.get('name')}:{c.get('type')}")
            else:
                col_sigs.append(str(c))
        parts.append(f"{tbl}:({','.join(col_sigs)})")
    if not parts and tables:
        parts = [f"tables:{','.join(sorted(tables))}"]
    raw_sig = "|".join(parts) or "empty_schema"
    return hashlib.sha256(raw_sig.encode("utf-8")).hexdigest()[:16]


def _generate_cache_key(schema_signature: str, question: str, language: str, context_sig: str = "") -> str:
    """Generate a deterministic SHA-256 cache key from schema, question, language, and context."""
    norm_q = " ".join(question.strip().lower().split())
    norm_lang = (language or "auto").strip().lower()
    raw = f"{schema_signature}::{norm_q}::{norm_lang}::{context_sig}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _get_from_cache(cache_key: str) -> Optional[Dict[str, Any]]:
    """Retrieve entry from cache if present and not expired; evict on read if expired."""
    entry = _QUERY_CACHE.get(cache_key)
    if not entry:
        return None

    now = time.time()
    created_at = entry.get("created_at", 0)
    age = now - created_at

    if age > CACHE_TTL_SECONDS:
        # Expired: evict on read
        _QUERY_CACHE.pop(cache_key, None)
        logger.info(
            "[Cache EVICT] Evicted expired cache entry %s (age: %.1fs > %ds)",
            cache_key[:12],
            age,
            int(CACHE_TTL_SECONDS),
        )
        return None

    logger.info(
        "[Cache HIT] Reusing cached Gemini response for key %s (age: %.1fs, TTL: %ds)",
        cache_key[:12],
        age,
        int(CACHE_TTL_SECONDS),
    )
    return copy.deepcopy(entry["response"])


def _put_in_cache(cache_key: str, response_data: Dict[str, Any]) -> None:
    """Store full Gemini response in the in-memory cache with current timestamp."""
    _QUERY_CACHE[cache_key] = {
        "response": copy.deepcopy(response_data),
        "created_at": time.time(),
    }
    logger.info(
        "[Cache STORE] Cached Gemini response for key %s (TTL: %ds)",
        cache_key[:12],
        int(CACHE_TTL_SECONDS),
    )


def clear_query_cache(session_id: Optional[str] = None) -> None:
    """Clear query cache globally or for a specific session."""
    count = len(_QUERY_CACHE)
    _QUERY_CACHE.clear()
    logger.info("[Cache CLEAR] Cleared %d cached response entries.", count)


def get_cache_size() -> int:
    """Return the number of entries currently stored in the query cache."""
    return len(_QUERY_CACHE)


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
            constraints = []
            if c.get("primary_key"):
                constraints.append("PRIMARY KEY")
            if c.get("nullable") is False:
                constraints.append("NOT NULL")
            constraints_str = f", {', '.join(constraints)}" if constraints else ""

            samples = c.get("sample_values")
            if not samples and sample_values_map and table in sample_values_map:
                samples = sample_values_map[table].get(col_name)
            samples = samples or []
            if samples:
                samples_str = ", ".join(repr(s) if isinstance(s, str) else str(s) for s in samples)
                if col_type:
                    col_strs.append(f"{col_name} ({col_type}{constraints_str}, sample values: {samples_str})")
                else:
                    col_strs.append(f"{col_name} (sample values: {samples_str}{constraints_str})")
            else:
                if col_type:
                    col_strs.append(f"{col_name} ({col_type}{constraints_str})")
                else:
                    col_strs.append(f"{col_name}{constraints_str}")
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


def generate_sql(
    session_id: str,
    nl_question: str,
    language: str = "auto",
    conversation_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Generate SQL from natural language question using Gemini with clarification, follow-ups, and model fallback.

    Returns:
        dict: {
            "needs_clarification": bool,
            "clarification_question": Optional[str],
            "query_type": str,  # 'select' or 'write'
            "sql": Optional[str],
            "explanation": Optional[str],
            "confidence": float
        }
    """
    global _WORKING_MODEL

    session = get_session(session_id)
    if not session:
        raise ValueError(f"Session '{session_id}' not found. Please connect to a database first.")

    # ---------------------------------------------------------------------------
    # Response Caching: key = SHA256(schema_sig + normalized_question + language + context)
    # ---------------------------------------------------------------------------
    schema_sig = _compute_schema_signature(session)
    context_sig = (
        f"{conversation_context.get('previous_question', '')}::{conversation_context.get('previous_sql', '')}"
        if conversation_context
        else ""
    )
    cache_key = _generate_cache_key(schema_sig, nl_question, language, context_sig)

    cached_resp = _get_from_cache(cache_key)
    if cached_resp is not None:
        logger.info(
            "[Cache HIT] Skipping Gemini API call; reusing cached response for query: '%s' (key: %s)",
            nl_question,
            cache_key[:12],
        )
        return cached_resp

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

    # Contextual awareness snippet for follow-up queries
    context_instruction = ""
    if conversation_context and conversation_context.get("previous_question"):
        prev_q = conversation_context.get("previous_question", "")
        prev_sql = conversation_context.get("previous_sql", "")
        context_instruction = f"""
5. Conversational Follow-Up Context:
   - Previous question: "{prev_q}"
   - Previous generated SQL: "{prev_sql}"
   - If the current user question is a follow-up or refinement (e.g., "what about last month?", "only for females", "by product"), interpret it in the context of the previous query and build upon or adjust the previous SQL logic.
"""

    base_prompt = f"""You are an expert SQLite SQL engineer and database analyst.
Given the following SQLite database schema:
{schema_str}

Instructions:
1. Data Availability Assessment (HIGHEST PRIORITY - Must Check FIRST Before Clarification):
   - You MUST FIRST check whether the requested table, entity, or core concept exists in the database schema above.
   - For example: if the user asks for 'patients', 'doctors', or 'patient records', but the schema only contains ecommerce tables ('customers', 'orders', 'products') — patient data DOES NOT EXIST in this database.
   - If the requested data/entity is NOT tracked in the schema:
     - Set "data_available": false
     - Set "unavailable_message": a clear, polite explanation (e.g. "This database tracks ecommerce orders, customers, and products, and does not contain patient data.").
     - Set "sql": null
     - Set "explanation": null
     - Set "needs_clarification": false
     - Set "confidence": 0.85
     - CRITICAL: Do NOT set "needs_clarification": true when the requested entity is absent from the database! Even if the user says 'top patients' or 'best doctors', if the entity does not exist in the schema, it is DATA UNAVAILABLE ("data_available": false), NOT a clarification question.

2. Speech-to-Text Correction & Interpreted Text:
   - The user's input may come from speech recognition, which occasionally mishears words (for example: "shom me pashents older then fourty").
   - Always return an "interpreted_text" field in the JSON response with the corrected sentence.
   - If you corrected any misspelled or phonetically misheard words between the user's input and "interpreted_text", provide them in "corrected_terms" as a list of {{"original": "misheard_word", "corrected": "fixed_word"}}.
   - CRITICAL RULES FOR corrected_terms:
     - corrected_terms must ONLY correct words that closely match actual schema terms (table names, column names from the connected database, or common query vocabulary like "top", "average", "delete").
     - If a word could plausibly be a data value (a proper noun, a name, capitalized mid-sentence, or simply doesn't closely resemble any schema term), it must NOT be included in corrected_terms, even if it superficially resembles a schema word.
     - EXACT CALIBRATION EXAMPLE: "Pavai" in "delete the age of patient Pavai" is a person's name (a data value), NOT a misspelling of "patients" — do NOT flag it in corrected_terms, keep "Pavai" intact in interpreted_text, and reference the literal value 'Pavai' in a WHERE clause.
     - Example valid schema correction: [{{"original": "paiens", "corrected": "patients"}}, {{"original": "fourty", "corrected": "forty"}}]
   - If no schema words were corrected, return [].
   - Base your SQL generation on this corrected "interpreted_text".

3. Clarification & Ambiguity Assessment (ONLY IF data IS available in the schema):
   - Only evaluate this if the requested entity actually exists in the schema.
   - Set "needs_clarification" to true when:
     - A ranking word is used ("top", "best", "highest", "most", "lowest", "yaaru top", "சிறந்த", etc.) on an existing table without specifying BOTH a metric to rank by AND a number/limit (for example: "give me the top patients" or "top patients" on hospital schema is ambiguous, whereas "top 5 patients by number of appointments" specifies both metric and limit and is NOT ambiguous).
     - A vague qualitative term is used with no defined criteria ("important", "recent", "significant", "good", "bad", "mukkiyamaana") without a clear threshold or timeframe.
     - The question could reasonably map to more than one table or column and the correct one cannot be inferred from the schema.
   - Otherwise, if the question has clear criteria or explicit filtering (for example: "list all patients older than 40"), set "needs_clarification" to false.

4. Language & Dialect Understanding (English, Tamil, and Thanglish):
   - Understand the intent accurately whether the user writes in English, Tamil script, or Thanglish (Tamil words written in Latin/English script).
   - Thanglish calibrations:
     - "40 vayasuku mela patients kaatu" means "show/list patients older than 40".
     - "doctor ellam list pannu" means "list all doctors".
{context_instruction}
6. Multi-Statement Queries & Controlled Write Operations:
   - Schema-destructive DDL operations (DROP TABLE, DROP DATABASE, ALTER TABLE, TRUNCATE, CREATE) are STRICTLY FORBIDDEN and dangerous. If the user asks to drop, delete tables, or alter schema, DO NOT generate a DROP or DDL statement. Set "sql": null, set "explanation": "Dropping tables or modifying database schema is strictly prohibited.", set "query_type": "select", "confidence": 0.0.
   - Multiple queries separated by semicolons (;) are fully supported.
   - If the user asks to insert, update, or delete data AND also asks to return, show, list, or view data (e.g. "Add patient X ... and return the full patients table", "Insert new appointment ... and show appointments"):
     - You MUST generate BOTH statements in sequence separated by a semicolon (;).
     - Example: INSERT INTO patients (name, age, gender, diagnosis, admission_date) VALUES ('Prem', 8, 'Male', 'Headache', '2026-04-23'); SELECT * FROM patients;
     - Set "query_type": "write".
     - In "explanation", explicitly mention both operations (adding the record and retrieving the table).
   - If the user asks to "delete / remove / clear the <column> of <entity>" (e.g. "delete the age of the patient pavai", "remove diagnosis of patient 3", "clear city of customer John"):
     - This is an attribute clearing operation, NOT a row or table deletion!
     - You MUST generate an UPDATE query setting that specific column to NULL:
       e.g. UPDATE patients SET age = NULL WHERE LOWER(name) = 'pavai';
     - Do NOT generate a DELETE query unless the user specifically asks to delete the record/patient/row itself.
     - ALWAYS use case-insensitive matching (e.g. LOWER(name) = 'pavai' or name LIKE 'Pavai') to ensure the row matches regardless of casing.
     - Set "query_type": "write".
   - If the user only asks to modify data (without asking to return/view data):
     - Generate the appropriate INSERT, UPDATE, or DELETE query.
     - For UPDATE and DELETE: You MUST ALWAYS include a precise WHERE clause targeting only the requested rows.
     - Set "query_type": "write".
   - If the user asks multiple read queries (e.g. "Count of patients and count of doctors"):
     - You can generate multiple SELECT statements separated by a semicolon: e.g. SELECT COUNT(*) AS total_patients FROM patients; SELECT COUNT(*) AS total_doctors FROM doctors;
     - Set "query_type": "select".
   - For all read-only queries, set "query_type": "select".

7. Output Structure Rules:
   - If "data_available" is false:
     - "data_available": false
     - "unavailable_message": a calm informational message
     - "corrected_terms": [...]
     - "needs_clarification": false
     - "clarification_question": null
     - "interpreted_text": the corrected/cleaned input question
     - "query_type": "select"
     - "sql": null
     - "explanation": null
     - "confidence": 0.85
   - Else if "needs_clarification" is true:
     - "data_available": true
     - "unavailable_message": null
     - "corrected_terms": [...]
     - "needs_clarification": true
     - "clarification_question": a short, specific, polite question asking the user to clarify the ambiguity.
     - "interpreted_text": the corrected/cleaned version of the input question.
     - "query_type": "select"
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
     - "query_type": "write" if any statement performs an insert/update/delete, otherwise "select"
     - "sql": valid, executable SQLite query statement(s) (use semicolons if multiple statements were requested) that accurately answer the question based on the interpreted text.
     - "explanation": a concise explanation of how the query operates.
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
  "query_type": "select",
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
            response = model.generate_content(
                base_prompt,
                generation_config=gen_config,
                request_options={"timeout": 30.0},
            )
            raw_text = response.text or ""
            cleaned = _clean_json_string(raw_text)

            try:
                data = json.loads(cleaned)
                _validate_result(data, nl_question, filtered_schema)
                _enforce_language(data, detected_lang, model)
                data["relevant_tables"] = relevant_tables
                _WORKING_MODEL = model_name
                _put_in_cache(cache_key, data)
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
1. FIRST check if the requested entity/data exists in the schema. If absent, set "data_available": false, provide "unavailable_message", set sql to null, needs_clarification: false. Do not ask for clarification if data does not exist in schema.
2. Determine if the question needs clarification (ONLY IF data exists in schema: e.g. ranking word without metric and limit on existing tables).
3. Fix speech-to-text mistakes in interpreted_text and list {{"original", "corrected"}} pairs in corrected_terms ONLY for schema keywords or SQL terms (never person names, proper nouns, or data values like 'Pavai').
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
                _validate_result(retry_data, nl_question, filtered_schema)
                _enforce_language(retry_data, detected_lang, model)
                retry_data["relevant_tables"] = relevant_tables
                _WORKING_MODEL = model_name
                _put_in_cache(cache_key, retry_data)
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

    logger.warning("All Gemini model generation attempts failed with error: %s. Using graceful clarification fallback.", last_error)
    return {
        "data_available": True,
        "unavailable_message": None,
        "corrected_terms": _extract_word_corrections(nl_question, nl_question),
        "needs_clarification": True,
        "clarification_question": "I could not generate a SQL query for this question right now. Could you please clarify your request with more specific criteria or table names?",
        "interpreted_text": nl_question,
        "sql": None,
        "explanation": None,
        "confidence": 0.2,
        "detected_language": detected_lang,
        "relevant_tables": relevant_tables,
    }



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


def _validate_result(data: Any, nl_question: str = "", schema: Optional[Dict[str, Any]] = None) -> None:
    """Ensure result dictionary contains required fields with expected types."""
    if not isinstance(data, dict):
        return

    # Normalize interpreted_text
    interpreted = data.get("interpreted_text")
    if not interpreted or not isinstance(interpreted, str) or not interpreted.strip():
        data["interpreted_text"] = nl_question
    else:
        data["interpreted_text"] = interpreted.strip()

    # Check if the query references a core entity completely absent from schema
    data_available = bool(data.get("data_available", True))
    if schema:
        q_tokens = set(re.findall(r"\b[a-zA-Z]+\b", nl_question.lower()))
        schema_tokens = set()
        for tbl, cols in schema.items():
            schema_tokens.add(tbl.lower())
            for c in cols:
                c_name = c.get("name", "") if isinstance(c, dict) else str(c)
                schema_tokens.add(c_name.lower())

        foreign_entity_keywords = [
            "patient", "patients", "doctor", "doctors", "appointment", "appointments", "hospital",
            "customer", "customers", "order", "orders", "product", "products", "sales", "revenue",
            "student", "students", "course", "courses", "teacher", "teachers", "weather", "stocks"
        ]
        for ek in foreign_entity_keywords:
            if ek in q_tokens and not any(ek in st for st in schema_tokens):
                data_available = False
                data["data_available"] = False
                data["unavailable_message"] = f"This database does not contain information about {ek}."
                data["sql"] = None
                data["explanation"] = None
                data["needs_clarification"] = False
                data["clarification_question"] = None
                break

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

    # Normalize corrected_terms (ensure proper nouns, names, and data values are not flagged as typos)
    corrected_terms = data.get("corrected_terms")
    valid_pairs = []
    sql_text = str(data.get("sql") or "").lower()
    if isinstance(corrected_terms, list):
        for item in corrected_terms:
            if isinstance(item, dict) and "original" in item and "corrected" in item:
                orig = str(item["original"]).strip()
                corr = str(item["corrected"]).strip()
                if orig and corr and orig.lower() != corr.lower():
                    # Safeguard: Do not flag names or data values that appear as literal values in the generated SQL
                    orig_l = orig.lower()
                    if f"'{orig_l}'" in sql_text or f'"{orig_l}"' in sql_text or f"%{orig_l}%" in sql_text:
                        continue
                    valid_pairs.append({"original": orig, "corrected": corr})
    # If model did not output pairs but input was corrected, derive automatically
    if not valid_pairs and data.get("interpreted_text") and nl_question:
        extracted = _extract_word_corrections(nl_question, data["interpreted_text"])
        for p in extracted:
            orig_l = p["original"].lower()
            if f"'{orig_l}'" in sql_text or f'"{orig_l}"' in sql_text or f"%{orig_l}%" in sql_text:
                continue
            valid_pairs.append(p)
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
            explanation = (data.get("explanation") or "").strip()
            data["needs_clarification"] = True
            data["clarification_question"] = explanation or "Could you please clarify your request?"
            data["sql"] = None
            data["confidence"] = 0.3
        else:
            data["sql"] = sql.strip()
            upper_sql = data["sql"].upper()
            if any(upper_sql.startswith(k) for k in ("DROP", "ALTER", "TRUNCATE", "CREATE")):
                data["sql"] = None
                data["explanation"] = "Schema modification operations (such as DROP or ALTER TABLE) are prohibited."
                data["confidence"] = 0.0
                data["query_type"] = "select"
            elif upper_sql.startswith("INSERT") or upper_sql.startswith("UPDATE") or upper_sql.startswith("DELETE"):
                data["query_type"] = "write"
                explanation = data.get("explanation")
                data["explanation"] = explanation.strip() if isinstance(explanation, str) else ""
                try:
                    conf = float(data.get("confidence", 0.9))
                    data["confidence"] = max(conf, 0.5)
                except (ValueError, TypeError):
                    data["confidence"] = 0.9
            else:
                data["query_type"] = data.get("query_type", "select")
                if data["query_type"] not in ("select", "write"):
                    data["query_type"] = "select"
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
                _validate_result(data, original_question, filtered_schema)
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
                _validate_result(retry_data, original_question, filtered_schema)
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

