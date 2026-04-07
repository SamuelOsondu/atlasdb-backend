# Stack and Infrastructure — AtlasDB

## Language

Python 3.12+

## Framework

FastAPI — async-first, built-in OpenAPI docs, excellent dependency injection, strong typing with Pydantic v2

## ORM and Migrations

- SQLAlchemy 2.x (async mode via `asyncpg`)
- Alembic for schema migrations
- All DB interactions through async sessions

## Database

PostgreSQL 16+ with pgvector extension enabled

## Vector Storage

pgvector (extension on PostgreSQL). No separate vector database service. Keeps infrastructure lean.

- Embedding dimension: 1536 (for `text-embedding-3-small`)
- Index type: IVFFlat with cosine distance
- Index applied to `document_chunks.embedding` column

## Queue

Celery 5.x
- Broker: Redis
- Result backend: Redis
- Task routing: separate queues for CPU-bound (extract/chunk) and I/O-bound (embed/index) work to prevent head-of-line blocking at scale
- Monitoring: Flower (optional, for dev/ops visibility)

## Caching

Redis
- Used as Celery broker + result backend
- Future use: cache frequent query embeddings or search results

## File Storage

Abstracted via a storage interface (`app/core/storage.py`)
- `STORAGE_BACKEND=local` → local filesystem (dev)
- `STORAGE_BACKEND=s3` → boto3/S3-compatible (production)
- Files stored with UUID-based filenames to avoid collisions

## AI/ML

- **Embedding model**: `text-embedding-3-small` (OpenAI) — 1536 dimensions, cost-efficient
- **LLM model**: `gpt-4o-mini` (configurable via `LLM_MODEL` env var)
- **Client**: `openai` Python SDK (async client)

## HTTP Validation

Pydantic v2 for all request/response schemas

## Rate Limiting

`slowapi` (FastAPI-compatible) on LLM-intensive endpoints

## Authentication

- `python-jose[cryptography]` for JWT signing/verification
- `passlib[bcrypt]` for password hashing
- Access token TTL: 15 minutes
- Refresh token TTL: 7 days, stored in DB for revocation support

## Deployment

Docker + Docker Compose
- `api` service: FastAPI app (uvicorn)
- `worker` service: Celery worker
- `db` service: PostgreSQL + pgvector
- `redis` service: Redis
- `flower` service: Celery monitoring (optional)

## Environment Configuration

All secrets and config via environment variables. `.env` file for local dev. Never committed.

Key variables:
```
DATABASE_URL
REDIS_URL
OPENAI_API_KEY
JWT_SECRET_KEY
JWT_ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=15
REFRESH_TOKEN_EXPIRE_DAYS=7
STORAGE_BACKEND=local
STORAGE_LOCAL_PATH=./uploads
S3_BUCKET_NAME
S3_REGION
LLM_MODEL=gpt-4o-mini
EMBEDDING_MODEL=text-embedding-3-small
MAX_CHUNKS_PER_QUERY=8
```

## Dependencies (verify versions before locking)

Verify current stable versions on PyPI before pinning. Key packages:
- `fastapi`
- `uvicorn[standard]`
- `sqlalchemy[asyncio]`
- `asyncpg`
- `alembic`
- `pydantic[email]`
- `celery[redis]`
- `openai`
- `python-jose[cryptography]`
- `passlib[bcrypt]`
- `slowapi`
- `python-multipart` (for file uploads)
- `pypdf2` or `pdfplumber` (PDF text extraction)
- `tiktoken` (token counting for context assembly)
- `pgvector` (SQLAlchemy integration)
- `boto3` (S3 storage)
- `flower` (Celery monitoring)
