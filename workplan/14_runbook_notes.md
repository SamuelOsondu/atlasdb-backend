# Runbook Notes — AtlasDB

## Local Development Setup

```bash
# 1. Copy env file
cp .env.example .env
# Fill in OPENAI_API_KEY, DATABASE_URL, REDIS_URL, JWT_SECRET_KEY

# 2. Start services
docker-compose up -d db redis

# 3. Run migrations
alembic upgrade head

# 4. Start API
uvicorn app.main:app --reload

# 5. Start Celery worker
celery -A app.celery_app worker --loglevel=info

# 6. (Optional) Start Flower
celery -A app.celery_app flower
```

## Docker Compose Start

```bash
docker-compose up --build
```

Services: `api`, `worker`, `db`, `redis`

## Running Migrations

```bash
# Generate migration after model change
alembic revision --autogenerate -m "description"

# Apply all pending migrations
alembic upgrade head

# Rollback one step
alembic downgrade -1
```

## Enabling pgvector

Migration `001` handles this. If running manually:
```sql
CREATE EXTENSION IF NOT EXISTS vector;
```
Must be run as superuser. Ensure the PostgreSQL image includes pgvector (use `pgvector/pgvector:pg16`).

## Building the IVFFlat Index

The IVFFlat index should be created after a significant number of chunks have been inserted, not on an empty table. The `lists` parameter should be approximately `sqrt(n_rows)`.

```sql
-- After data load
CREATE INDEX ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);
```

For initial deployment with small collections, a flat scan (no index) is acceptable until >10k chunks.

## Checking Document Processing Status

Via API:
```
GET /api/v1/documents/{document_id}
```
Returns `status`: `pending | processing | indexed | failed`

If `failed`, check `error_message` field for root cause.

## Reprocessing a Failed Document

Admin endpoint:
```
POST /api/v1/admin/documents/{document_id}/reprocess
```
Clears existing chunks, resets status to `pending`, re-enqueues processing job.

## Monitoring Celery Workers

```bash
# Via Flower (if running)
open http://localhost:5555

# Via CLI
celery -A app.celery_app inspect active
celery -A app.celery_app inspect stats
```

## Environment Variables Reference

| Variable | Required | Default | Description |
|---|---|---|---|
| DATABASE_URL | yes | — | PostgreSQL async URL (`postgresql+asyncpg://...`) |
| REDIS_URL | yes | — | Redis URL (`redis://localhost:6379/0`) |
| OPENAI_API_KEY | yes | — | OpenAI API key |
| JWT_SECRET_KEY | yes | — | Random 32+ char string |
| JWT_ALGORITHM | no | HS256 | JWT signing algorithm |
| ACCESS_TOKEN_EXPIRE_MINUTES | no | 15 | Access token TTL |
| REFRESH_TOKEN_EXPIRE_DAYS | no | 7 | Refresh token TTL |
| STORAGE_BACKEND | no | local | `local` or `s3` |
| STORAGE_LOCAL_PATH | no | ./uploads | Local file storage path |
| S3_BUCKET_NAME | if s3 | — | S3 bucket name |
| S3_REGION | if s3 | — | AWS region |
| LLM_MODEL | no | gpt-4o-mini | OpenAI chat model |
| EMBEDDING_MODEL | no | text-embedding-3-small | OpenAI embedding model |
| MAX_CHUNKS_PER_QUERY | no | 8 | Max context chunks for RAG |
| MAX_FILE_SIZE_MB | no | 50 | Upload file size limit |

## Recovery Procedures

### Documents stuck in `processing`
Check if Celery worker is running. If worker crashed mid-task, document may be stuck. Use admin reprocess endpoint to reset and retry.

### pgvector index degraded
After bulk deletes or chunk updates, VACUUM the table and rebuild index:
```sql
VACUUM ANALYZE document_chunks;
REINDEX INDEX <index_name>;
```

### OpenAI API key expired/rotated
Update `OPENAI_API_KEY` in environment and restart API + worker services. No DB changes needed.
