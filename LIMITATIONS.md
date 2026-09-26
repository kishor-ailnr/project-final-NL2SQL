# NL2SQL — Known Limitations & Production Roadmap

In compliance with engineering integrity principles, this document outlines the operational boundaries, design trade-offs, and future production enhancements of the NL2SQL system.

---

## 1. Current Boundaries & Limitations

### 1.1 Database Engine Scope
- **Implemented & Verified**: Full native support for SQLite files, demo databases, and CSV/SQL uploads. PostgreSQL connection adapter is fully scaffolded and tested for validation and query translation, but requires a live network-accessible PostgreSQL instance and `psycopg2` driver in production environments.
- **MySQL & Oracle**: Not currently bundled by default. MySQL connection strings will return a descriptive error informing the user to use SQLite or PostgreSQL, rather than pretending to work.

### 1.2 Rate Limiting & Scaling
- **In-Memory Rate Limiting**: The current rate limiter uses an in-memory sliding window (20 req/min per session, 100 req/min global).
- **Scale Target**: Fully optimized and stable for single-instance deployments (such as Render free-tier hosting 5–10 concurrent users).
- **Production Path**: For multi-instance, clustered horizontal scaling, rate limiting state and session storage should be backed by an external Redis cluster.

### 1.3 Voice Input
- **Client-Side Dependency**: Speech-to-text uses the browser's native Web Speech API (`webkitSpeechRecognition`).
- **Browser Compatibility**: Best supported in Google Chrome, Chromium-based browsers, and Edge. Unsupported browsers fall back cleanly to standard text input.
- **Audio File Uploads**: Direct raw `.wav`/`.webm` audio file binary uploads to the backend are not implemented; audio recognition is processed natively in the browser before being verified and corrected phonetically by the backend.

### 1.4 Write Confirmation Buffer
- **In-Memory Staging**: Staged write queries in `_PENDING_WRITES` are stored in memory with an eviction lifecycle. A server restart will clear unconfirmed write operations, requiring the user to re-issue the query.

---

## 2. Production Roadmap & Future Work
1. **Async Database Drivers**: Migrating adapter execution from synchronous `sqlite3` and `psycopg2` to `aiosqlite` and `asyncpg` for enhanced concurrent I/O throughput.
2. **Distributed Redis Session & Cache Store**: Moving the 10-minute response cache and session registry to Redis for multi-worker Uvicorn clusters.
3. **Fine-Tuned Open-Source LLMs**: Adding support for local self-hosted open-source models (e.g. CodeLlama or DeepSeek-Coder via vLLM) alongside Google Gemini.
