# API Integrations — AtlasDB

## 1. OpenAI API

### Purpose
- Embedding generation: convert text chunks and queries to vector representations
- LLM response generation: produce grounded answers from retrieved context

### Provider
OpenAI (or any OpenAI-compatible provider via `base_url` override)

### Authentication
Bearer token via `OPENAI_API_KEY` environment variable

### Models
- Embeddings: `text-embedding-3-small` (1536 dimensions)
- LLM: `gpt-4o-mini` (configurable via `LLM_MODEL` env var)

### API Usage Patterns

**Embeddings:**
- Called during document processing pipeline (per-chunk)
- Called per query before vector search
- Input: text string; Output: float array of 1536 dimensions
- Batch embedding supported for chunk processing (up to 2048 items per request)

**LLM (Chat Completions):**
- Called once per user query
- Streaming enabled via `stream=True`
- System prompt enforces grounding rules
- Input: system prompt + context chunks + conversation history + user query
- Output: streamed tokens forwarded via SSE

### Rate Limits
- Embeddings: RPM and TPM limits vary by tier — implement exponential backoff on 429
- Chat completions: same backoff strategy
- Celery task retry handles embedding rate limits
- LLM endpoint rate limiting via `slowapi` on client side

### Failure Modes
- 429 (rate limit): retry with exponential backoff in Celery tasks; return error in query endpoint
- 500 / 503 (OpenAI outage): fail task with `failed` status; return graceful error to user
- Context too long: enforced before API call via tiktoken token counting

### Retry Strategy
- Embedding generation tasks: max 3 retries, exponential backoff (30s, 90s, 270s)
- Query endpoint: no retry (user-facing, fail fast with clear error)

### Idempotency
- Embedding generation for a chunk is idempotent — same text produces same vector (deterministic)
- Chunk records include processing status to prevent re-embedding already processed chunks

### Sandbox / Testing
- Use `OPENAI_API_KEY` pointing to a test account or mock the client in tests
- Integration tests should mock OpenAI calls to avoid cost and flakiness

### Client Structure
`app/core/openai_client.py` — singleton async OpenAI client, initialized from config. Wraps embedding and chat calls with retry logic and error handling.

---

## 2. PostgreSQL / pgvector

Not an external API, but treated as first-class integration.

- pgvector extension must be enabled: `CREATE EXTENSION IF NOT EXISTS vector;`
- Migration must create the extension before any vector columns are created
- SQLAlchemy model uses `Vector(1536)` column type from `pgvector.sqlalchemy`

---

## 3. Redis

Not an external API.

- Celery broker and result backend
- Connection string via `REDIS_URL` env var
- Direct application reads/writes for: rate limiting state, query embedding cache, query cancellation registry, JWT denylist (in addition to Celery broker/results)

---

## 4. File Storage (S3-compatible)

### Providers
- Local filesystem (dev)
- AWS S3, MinIO, Cloudflare R2, or any S3-compatible (production)

### Authentication
- Local: no auth
- S3: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `S3_BUCKET_NAME`, `S3_REGION`

### Behavior
- Files uploaded with UUID-based keys to avoid collisions
- Files retrieved by key for text extraction during pipeline
- Deletion supported when documents are hard-deleted (rare — soft delete preferred)

### Client Structure
`app/core/storage.py` — abstract storage interface with `LocalStorage` and `S3Storage` implementations. Factory selects implementation based on `STORAGE_BACKEND` env var.
