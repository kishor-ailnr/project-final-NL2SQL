# NL2SQL — Complete API Reference Specification

All endpoints are served by the FastAPI backend at `http://localhost:8000` (or the configured host). All request and response bodies use JSON format unless specified otherwise.

---

## 1. Database Connection & Session Management

### `POST /api/connect-db`
Connects to an existing demo database, direct SQLite file, or live PostgreSQL database, extracts the complete schema, registers the adapter, and initializes a session.

#### Request Body
```json
{
  "db_type": "demo", // "demo", "sqlite", "postgres", "postgresql"
  "demo_name": "hospital", // Optional: "hospital" or "ecommerce"
  "connection_string": null // Optional: e.g. "sqlite:///path/to/db.db" or "postgresql://user:pass@host:5432/db"
}
```

#### Response (`200 OK`)
```json
{
  "session_id": "78b4081c-d812-4217-a0ee-6c188bfe4e95",
  "status": "connected",
  "tables": ["patients", "doctors", "appointments"]
}
```

---

### `POST /api/upload-db`
Uploads a `.csv` or `.sql` file, converts/executes it into a new isolated session SQLite database, extracts schema and sample values, and registers an adapter.

#### Request
- **Content-Type**: `multipart/form-data`
- **Body**: `file` (Binary file content, max 5 MB)

#### Response (`200 OK`)
```json
{
  "session_id": "93f2187d-080b-42ab-ba41-11883be7dc2b",
  "status": "connected",
  "tables": ["uploaded_data"]
}
```

---

### `GET /api/session-status`
Checks if a session is currently active or restorable.

#### Query Parameters
- `session_id` (string, required)

#### Response (`200 OK`)
```json
{
  "valid": true,
  "status": "connected",
  "session_id": "78b4081c-d812-4217-a0ee-6c188bfe4e95",
  "tables": ["patients", "doctors", "appointments"]
}
```

---

## 2. Natural Language Query & Execution

### `POST /api/query`
Translates natural language questions into SQL, performs RAG retrieval, runs AST validation, checks data availability, clarifies ambiguities, manages conversational follow-ups, and executes queries or stages writes.

#### Request Body
```json
{
  "session_id": "78b4081c-d812-4217-a0ee-6c188bfe4e95",
  "conversation_id": "conv-uuid-1234", // Optional
  "text": "Show all patients older than 50",
  "language": "auto" // "auto", "english", "tamil", "thanglish"
}
```

#### Response (`200 OK`) — Read Query
```json
{
  "query_id": "1",
  "sql": "SELECT * FROM patients WHERE age > 50;",
  "explanation": "Retrieves all patient records where the age exceeds 50 years.",
  "confidence": 0.95,
  "needs_clarification": false,
  "clarification_question": null,
  "query_type": "select",
  "result": [
    { "id": 1, "name": "Arun Kumar", "age": 52, "gender": "M", "diagnosis": "Hypertension" }
  ],
  "chart_type": "none",
  "interpreted_text": "Show all patients older than 50",
  "detected_language": "english",
  "self_corrected": false,
  "correction_attempts": 0,
  "data_available": true,
  "unavailable_message": null,
  "corrected_terms": []
}
```

#### Response (`200 OK`) — Staged Write Query
```json
{
  "query_id": "2",
  "sql": "UPDATE patients SET age = 53 WHERE id = 1;",
  "explanation": "Updates the age to 53 for patient with id 1.",
  "confidence": 0.95,
  "needs_clarification": false,
  "clarification_question": null,
  "query_type": "write",
  "result": [],
  "chart_type": "none",
  "interpreted_text": "Update age to 53 for patient with id 1",
  "detected_language": "english",
  "self_corrected": false,
  "correction_attempts": 0,
  "data_available": true,
  "unavailable_message": null,
  "corrected_terms": []
}
```

#### Response (`200 OK`) — Ambiguous Query (Clarification Required)
```json
{
  "query_id": "3",
  "sql": null,
  "explanation": null,
  "confidence": 0.3,
  "needs_clarification": true,
  "clarification_question": "Do you want top patients ranked by age, total billing amount, or number of appointments?",
  "query_type": "select",
  "result": [],
  "chart_type": "none",
  "interpreted_text": "Give me the top patients",
  "detected_language": "english",
  "data_available": true
}
```

---

### `POST /api/confirm-write`
Confirms or cancels execution of a staged write SQL operation.

#### Request Body
```json
{
  "session_id": "78b4081c-d812-4217-a0ee-6c188bfe4e95",
  "query_id": "2",
  "confirmed": true // true to execute, false to cancel
}
```

#### Response (`200 OK`)
```json
{
  "status": "executed", // "executed", "cancelled", or "error"
  "rows_affected": 1,
  "error": null
}
```

---

## 3. Conversation & Chat Management

### `POST /api/conversations/new`
Creates a new conversation thread for a session.

#### Request Body
```json
{
  "session_id": "78b4081c-d812-4217-a0ee-6c188bfe4e95"
}
```

#### Response (`200 OK`)
```json
{
  "conversation_id": "conv-a1b2c3d4",
  "created_at": "2026-09-25T17:15:00.000Z"
}
```

---

### `GET /api/conversations`
Lists all conversations associated with a session.

#### Query Parameters
- `session_id` (string, required)

#### Response (`200 OK`)
```json
{
  "conversations": [
    {
      "conversation_id": "conv-a1b2c3d4",
      "title": "Patients older than 50",
      "created_at": "2026-09-25T17:15:00.000Z"
    }
  ]
}
```

---

### `GET /api/conversations/{conversation_id}/messages`
Retrieves message and query history for a conversation thread.

#### Path Parameters
- `conversation_id` (string, required)

#### Response (`200 OK`)
```json
{
  "messages": [
    {
      "nl_query": "Show all patients older than 50",
      "sql": "SELECT * FROM patients WHERE age > 50;",
      "explanation": "Retrieves all patient records where the age exceeds 50 years.",
      "result": [{ "id": 1, "name": "Arun Kumar", "age": 52 }],
      "chart_type": "none",
      "timestamp": "2026-09-25T17:15:02.000Z"
    }
  ]
}
```

---

### `DELETE /api/conversations/{conversation_id}`
Deletes a conversation and its recorded query history.

#### Path Parameters
- `conversation_id` (string, required)

#### Response (`200 OK`)
```json
{
  "status": "deleted"
}
```

---

## 4. System Health

### `GET /health`
Liveness and readiness check.

#### Response (`200 OK`)
```json
{
  "status": "ok",
  "service": "nl2sql-backend"
}
```
