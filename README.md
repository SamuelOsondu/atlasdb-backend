# AtlasDB

A production-ready RAG (Retrieval-Augmented Generation) backend that turns your documents into a semantically searchable knowledge base with grounded, citation-backed conversational answers.

---

## What it does

1. **Upload documents** (PDF, Markdown, plain text) into knowledge domains
2. **Auto-processes** them asynchronously — text extraction → chunking → embedding → pgvector indexing
3. **Semantic search** — query across all your documents or scope to a specific domain
4. **Conversational RAG** — ask follow-up questions in a conversation session; the backend retrieves relevant chunks, assembles a context-bounded prompt, and streams the LLM response back token-by-token via SSE
5. **Citations on every answer** — every response references the exact document chunks used to generate it

---

## Tech Stack

| Layer | Technology |
|---|---|
| API | FastAPI (Python 3.12+) |
| Database | PostgreSQL 16 + pgvector |
| ORM | SQLAlchemy 2.x async + Alembic |
| Queue | Celery 5 (Redis broker) |
| Cache / Cancellation | Redis |
| Embeddings | OpenAI `text-embedding-3-small` |
| LLM | OpenAI `gpt-4o-mini` (configurable) |
| Auth | JWT (access + refresh tokens) |
| File Storage | Local filesystem (dev) / S3-compatible (prod) |
| Rate Limiting | slowapi |
| Streaming | Server-Sent Events (SSE) |

---

## Project Structure

```
app/
├── core/           # Config, DB session, security, dependencies, Redis, OpenAI client
├── auth/           # Register, login, refresh, logout
├── users/          # Profile management, admin controls
├── domains/        # Knowledge domain CRUD
├── documents/      # File upload, metadata, status tracking
├── processing/     # Celery pipeline: extract → chunk → embed → index
├── retrieval/      # Semantic search (pgvector cosine similarity)
├── conversations/  # Conversation sessions + message history
├── query_engine/   # RAG orchestration: context assembly, LLM streaming, citations
└── shared/         # Unified response schemas, enums, pagination
alembic/            # Database migrations
tests/              # Full test suite (per component)
```

---

## API Overview

All responses use a unified envelope:
```json
{ "success": true, "data": { ... }, "message": "..." }
```

### Auth
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/auth/register` | Create account |
| POST | `/api/v1/auth/login` | Get access + refresh tokens |
| POST | `/api/v1/auth/refresh` | Rotate refresh token |
| POST | `/api/v1/auth/logout` | Revoke refresh token |

### Domains
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/domains` | Create knowledge domain |
| GET | `/api/v1/domains` | List your domains |
| GET | `/api/v1/domains/{id}` | Get domain |
| PATCH | `/api/v1/domains/{id}` | Update domain |
| DELETE | `/api/v1/domains/{id}` | Delete domain (cascades to documents) |

### Documents
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/domains/{id}/documents` | Upload document (triggers async processing) |
| GET | `/api/v1/domains/{id}/documents` | List documents in domain |
| GET | `/api/v1/documents/{id}` | Get document + status |
| DELETE | `/api/v1/documents/{id}` | Soft-delete document |

### Search
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/search` | Semantic search (optionally scope by domain) |

### Conversations
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/conversations` | Create conversation |
| GET | `/api/v1/conversations` | List conversations |
| GET | `/api/v1/conversations/{id}` | Get conversation |
| DELETE | `/api/v1/conversations/{id}` | Delete conversation |
| GET | `/api/v1/conversations/{id}/messages` | Paginated message history (cursor-based) |

### Query Engine (RAG + Streaming)
| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/v1/conversations/{id}/query` | Submit query — streams SSE response |
| DELETE | `/api/v1/conversations/{id}/query/{request_id}` | Cancel in-flight query |

#### SSE Event Format
```
data: {"request_id": "uuid"}        ← first event (use for cancellation)

data: {"token": "Paris"}            ← streamed tokens
data: {"token": " is the capital"}

data: {"done": true, "citations": [
  {"doc_id": "...", "doc_title": "Europe Guide", "chunk_index": 0, "excerpt": "..."}
]}                                  ← final event

data: {"cancelled": true}           ← if cancelled mid-stream
data: {"error": "..."}              ← on failure
```

**Rate limited:** 10 requests/minute per user on the query endpoint.

---

## Getting Started

### Prerequisites
- Docker + Docker Compose
- An OpenAI API key

### 1. Clone and configure

```bash
git clone https://github.com/your-username/atlasdb-backend.git
cd atlasdb-backend

cp .env.example .env
# Edit .env and set OPENAI_API_KEY and JWT_SECRET_KEY
```

### 2. Start all services

```bash
docker-compose up --build
```

This starts:
- `api` — FastAPI on http://localhost:8000
- `worker-cpu` — Celery worker for text extraction and chunking
- `worker-io` — Celery worker for embedding and indexing
- `db` — PostgreSQL 16 with pgvector
- `redis` — Redis (broker + cancellation store)
- `flower` — Celery monitoring UI on http://localhost:5555

### 3. Run migrations

```bash
docker-compose exec api alembic upgrade head
```

### 4. Explore the API

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health check: http://localhost:8000/health

---

## Local Development (without Docker)

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate

pip install -r requirements.txt

cp .env.example .env
# Set DATABASE_URL, REDIS_URL, OPENAI_API_KEY, JWT_SECRET_KEY in .env

alembic upgrade head

uvicorn app.main:app --reload
```

---

## Running Tests

```bash
pytest
```

Tests use an in-memory SQLite-compatible async setup — no real database or OpenAI calls required. External calls (embeddings, LLM streaming) are monkeypatched.

---

## Environment Variables

| Variable | Required | Default | Description |
|---|---|---|---|
| `DATABASE_URL` | ✅ | — | PostgreSQL async connection string |
| `REDIS_URL` | ✅ | `redis://localhost:6379/0` | Redis connection string |
| `OPENAI_API_KEY` | ✅ | — | OpenAI API key |
| `JWT_SECRET_KEY` | ✅ | — | Secret for signing JWTs |
| `JWT_ALGORITHM` | | `HS256` | JWT signing algorithm |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | | `15` | Access token TTL |
| `REFRESH_TOKEN_EXPIRE_DAYS` | | `7` | Refresh token TTL |
| `LLM_MODEL` | | `gpt-4o-mini` | OpenAI chat model |
| `EMBEDDING_MODEL` | | `text-embedding-3-small` | OpenAI embedding model |
| `STORAGE_BACKEND` | | `local` | `local` or `s3` |
| `STORAGE_LOCAL_PATH` | | `./uploads` | Local file storage path |
| `S3_BUCKET_NAME` | S3 only | — | S3 bucket name |
| `S3_REGION` | S3 only | — | AWS region |
| `S3_ACCESS_KEY_ID` | S3 only | — | AWS access key |
| `S3_SECRET_ACCESS_KEY` | S3 only | — | AWS secret key |
| `MAX_FILE_SIZE_MB` | | `50` | Max upload size |
| `MAX_CHUNKS_PER_QUERY` | | `8` | Max chunks used per RAG query |
| `CONTEXT_TOKEN_BUDGET` | | `6000` | Token budget for assembled context |

---

## Key Design Decisions

- **Modular monolith** — single codebase, clear module boundaries, no premature microservices split
- **pgvector over a dedicated vector DB** — keeps infrastructure lean; production-ready at this scale
- **SSE over WebSockets** — one-way streaming matches the use case; cancellation handled via REST + Redis flag
- **Ownership at the SQL level** — retrieval queries JOIN on `owner_id` so unauthorised chunks never reach Python
- **Cursor-based pagination for messages** — stable ordering even under concurrent writes
- **No partial persistence** — cancelled or errored queries never write to the DB; only a fully completed stream persists both the user message and assistant response

---

## License

MIT
