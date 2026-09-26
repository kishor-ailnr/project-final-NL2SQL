# NL2SQL — System Architecture Specification

## 1. High-Level Architectural Overview

NL2SQL is organized as a decoupled, multi-tiered architecture with a modern Single-Page Application (SPA) frontend and a Python FastAPI backend communicating over RESTful HTTP APIs.

```text
┌─────────────────────────────────────────────────────────────┐
│                       Client Layer                          │
│  React 18 + Vite + TailwindCSS + Web Speech API + Chart.js  │
└──────────────────────────────┬──────────────────────────────┘
                               │ JSON / HTTP REST
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                    API Gateway & Middleware                 │
│  - Security Headers (CSP, X-Frame-Options, nosniff)         │
│  - Two-Tier Sliding Window Rate Limiting (Session & Global) │
│  - Environment-Aware CORS Handling                          │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                      Core AI Pipeline                       │
│  1. Language Detection & Phonetic Mishearing Normalization  │
│  2. Schema-Aware Vector RAG (FAISS + all-MiniLM-L6-v2)      │
│  3. Data Availability & Ambiguity Verification Engine       │
│  4. Contextual Prompt Assembly & Gemini LLM Synthesis       │
│  5. AST SQL Validation & Multi-Statement Protection         │
│  6. Self-Correction Retry Loop (up to 3 retries)            │
│  7. Staged Write Confirmation Manager                       │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                Universal Database Abstraction               │
│  - BaseDatabaseAdapter Interface                            │
│  - SQLiteAdapter (Demo databases, CSV/SQL uploads, files)   │
│  - PostgreSQLAdapter (Direct PostgreSQL URI connections)    │
│  - DatabaseConnectionManager                                │
└──────────────────────────────┬──────────────────────────────┘
                               │
                               ▼
┌─────────────────────────────────────────────────────────────┐
│                      Persistence Layer                      │
│  - Session & Conversation Metadata Store (meta.db)          │
│  - In-Memory Response Cache (10-minute TTL)                 │
│  - Staged Write Buffer (_PENDING_WRITES)                    │
│  - Connected Database Engines                               │
└─────────────────────────────────────────────────────────────┘
```

---

## 2. Core Architectural Layers & Components

### 2.1 Universal Database Support Layer
Located in [`app/database/`](file:///c:/Music/NL2SQL/nl2sql-backend/app/database/):
- **[`BaseDatabaseAdapter`](file:///c:/Music/NL2SQL/nl2sql-backend/app/database/base.py)**: Abstract base class defining universal database methods:
  - `connect()` / `disconnect()`
  - `validate_connection() -> bool`
  - `get_tables() -> List[str]`
  - `get_columns(table_name) -> List[Dict[str, Any]]`
  - `get_primary_keys(table_name) -> List[str]`
  - `get_foreign_keys(table_name) -> List[Dict[str, Any]]`
  - `get_sample_values(table_name, col_name, limit) -> List[Any]`
  - `get_row_count(table_name) -> int`
  - `extract_full_schema() -> Dict[str, Any]`
  - `execute_query(sql) -> List[Dict[str, Any]]`
  - `execute_write(sql) -> Dict[str, Any]` (transactional rollback on failure)
- **[`SQLiteAdapter`](file:///c:/Music/NL2SQL/nl2sql-backend/app/database/sqlite_adapter.py)**: Concrete adapter for SQLite database files and demo datasets.
- **[`PostgreSQLAdapter`](file:///c:/Music/NL2SQL/nl2sql-backend/app/database/postgres_adapter.py)**: Concrete adapter for PostgreSQL connections with graceful fallback when optional drivers are unconfigured.
- **[`DatabaseConnectionManager`](file:///c:/Music/NL2SQL/nl2sql-backend/app/database/manager.py)**: Factory and registry maintaining active adapter instances keyed by `session_id`.

### 2.2 Schema-Aware Retrieval (RAG)
Located in [`app/services/rag_service.py`](file:///c:/Music/NL2SQL/nl2sql-backend/app/services/rag_service.py):
- Embeds table schemas and descriptions using `sentence-transformers` (`all-MiniLM-L6-v2`) into a localized `FAISS` index per session.
- Small schemas ($\le 4$ tables) are preserved entirely to prevent losing table context.
- Large schemas ($> 4$ tables) dynamically retrieve the top-4 most semantically relevant tables, trimming irrelevant schema definitions before constructing the prompt.

### 2.3 Multilingual & Speech Understanding
Located in [`app/services/sql_generator.py`](file:///c:/Music/NL2SQL/nl2sql-backend/app/services/sql_generator.py):
- **Trilingual Processing**: Detects whether the input text is in English, Tamil script (Unicode `\u0B80`–`\u0BFF`), or Thanglish (Tamil vocabulary written in Latin characters).
- **Phonetic Mishearing Corrections**: Derives word-level corrections between raw speech and interpreted text, returning `corrected_terms` for user transparency.
- **Localized Responses**: Enforces explanations and clarifications in Tamil script when queried in Tamil, or with an explicit Thanglish acknowledgment in English.

### 2.4 Ambiguity & Data Availability Gates
1. **Data Availability Check**: Evaluates if the requested entity exists in the schema. If missing (e.g. asking for "hotel reservations" on a hospital database), it immediately outputs an informational message with `data_available: false` and `sql: null`.
2. **Clarification Check**: Identifies underspecified queries with unconstrained ranking words (e.g. "top patients", "best doctors") and halts execution to ask targeted clarifying questions.

### 2.5 AST SQL Validation & Safety Gate
Located in [`app/services/sql_validator.py`](file:///c:/Music/NL2SQL/nl2sql-backend/app/services/sql_validator.py):
- **AST Parsing**: Parses SQL statements with `sqlglot`.
- **Injection Prevention**: Blocks stacked semicolon-separated statements and SQL comments outside quotes.
- **Read/Write Segmentation**: Defaults to `allow_write=False`. When `allow_write=True`, safely permits `INSERT`, `UPDATE` (requiring `WHERE`), and `DELETE` (requiring `WHERE`), while unconditionally rejecting DDL (`DROP`, `ALTER`, `CREATE`, `TRUNCATE`).

### 2.6 Controlled Write Confirmation Workflow
1. Natural language write intent is detected and synthesized by Gemini (`query_type: "write"`).
2. SQL statement is validated by `validate_sql(sql, allow_write=True)`.
3. If valid, the write is staged in memory in `_PENDING_WRITES[query_id]`.
4. Response returns `query_type: "write"` with `result: []`.
5. Frontend opens `ConfirmModal.jsx` displaying the SQL statement and explanation.
6. User clicks Confirm $\rightarrow$ frontend calls `POST /api/confirm-write`.
7. Backend executes the statement inside a transactional block, commits the change, invalidates the response cache, and logs row count.

### 2.7 Conversational Context & Follow-Ups
- When a user submits a query within an existing conversation, the backend looks up the most recent query and generated SQL from [`QueryHistoryModel`](file:///c:/Music/NL2SQL/nl2sql-backend/app/models/meta_db.py).
- Passes `conversation_context` into `generate_sql()`.
- Incorporates conversational context into the cache key to guarantee accurate, non-conflicting caching across multi-turn chats.

### 2.8 In-Memory Response Caching
- Key: `SHA-256(schema_sig + normalized_question + language + context_sig)`.
- Value: Cached Gemini generation response with 10-minute TTL.
- Invalidation: Cache is automatically cleared upon any confirmed write execution.
