# Processing Pipeline Component

## Purpose
Performs all computationally intensive document processing asynchronously via Celery. Transforms a raw uploaded file into indexed, searchable chunks stored as pgvector embeddings. This component is entirely background — no user-facing HTTP endpoints.

## Scope

### In Scope
- Celery task definitions for each pipeline stage
- Text extraction from PDF, Markdown, plain text files
- Content chunking with configurable strategy
- Embedding generation via OpenAI `text-embedding-3-small`
- Batch insert of `DocumentChunk` records with embeddings into pgvector
- Document status updates throughout pipeline
- Retry logic for external API failures (embedding generation)

### Out of Scope
- File upload (owned by `documents`)
- Vector search/retrieval (owned by `retrieval`)
- Direct HTTP endpoints (none — background only)

## Responsibilities
- Retrieve file from storage backend using `document.file_key`
- Extract raw text from file (per file type: PDF, MD, TXT)
- Split text into semantic chunks (paragraph/section aware, token-aware)
- Generate embeddings for all chunks in batches
- Write `DocumentChunk` rows with embeddings to DB in a single transaction
- Update `Document.status` at each stage: `pending → processing → indexed | failed`
- Set `Document.error_message` on failure
- Set `Document.chunk_count` after chunking

## Dependencies
- `documents` (read Document record, update status)
- `core/storage.py` (fetch file by key)
- `core/openai_client.py` (embedding generation)
- `core/database.py` (sync session for Celery tasks)
- External: OpenAI API

## Related Models
- `Document` (read + status update)
- `DocumentChunk` (create)

## Related Endpoints
None — background tasks only.

## Business Rules
- Status must be updated to `processing` before any work begins (prevents duplicate jobs)
- If any stage fails after max retries, set `Document.status = "failed"` with error message
- Existing chunks must be cleared before reprocessing a document (avoid duplicates)
- Embedding generation must be batched: max 200 chunks per API call
- Token limit per chunk: 512 tokens (configurable) — chunker must enforce this
- Chunk overlap: 50 tokens (configurable) — improves retrieval context continuity
- Pipeline stages are chained: extract → chunk → embed → index (each stage is a separate Celery task)

## Security Considerations
- File content is processed in isolated worker process — API is not exposed to extracted text during processing
- OpenAI API key loaded from env in worker process
- No user input in pipeline (document_id only) — no injection surface

## Performance Considerations
- Embedding batching: batch 100-200 chunks per API call to reduce OpenAI requests
- Chunk insertion: bulk insert all chunks for a document in a single transaction
- Large PDFs may produce many chunks — worker should not load all into memory simultaneously; stream/process in pages
- Task timeout: set per-task timeout (e.g., 10 minutes) to prevent stuck workers

## Reliability Considerations
- Each pipeline stage is idempotent:
  - Extract: always re-extracts from file (file is source of truth)
  - Chunk: deterministic given same text
  - Embed: same text produces same embedding (OpenAI is deterministic for same model)
  - Index: clear existing chunks before re-inserting — prevents duplicates
- Retry on OpenAI API errors: exponential backoff, max 3 retries
- If worker crashes mid-pipeline: document status stays at last known state; reprocess endpoint resets to `pending`
- Chunk DB write failures: entire document fails, status set to `failed` — no partial writes

## Testing Expectations
- Unit: chunker (chunk boundary correctness, token limit enforcement, overlap)
- Unit: text extractor (PDF text extraction, Markdown parsing, plain text passthrough)
- Integration: full pipeline with mock OpenAI (mock embedding generation), real DB
  - Verify chunks created, document status = indexed, chunk_count correct
- Failure path: mock OpenAI returning 429 → verify retry behavior → eventual failure → status = failed
- Idempotency: run pipeline twice on same document → no duplicate chunks

## Implementation Notes
- `processing/tasks.py`: Celery task definitions. Use `bind=True` for self-retry.
  - `process_document(document_id)` — orchestration task that chains subtasks
  - Or chain: `extract_text.s(document_id) | chunk_document.s() | embed_chunks.s() | index_chunks.s()`
- `processing/extractors.py`: per-format extractors
  - PDFs: use `pdfplumber` (better than PyPDF2 for text layout preservation)
  - Markdown: `markdown-it-py` or plain regex strip
  - Plain text: passthrough with normalization
- `processing/chunker.py`: `chunk_text(text, max_tokens, overlap)` — returns list of `(chunk_text, metadata)`
  - Uses `tiktoken` for token counting
  - Splits on paragraph boundaries first, then sentence, then hard-split by token limit
- Celery tasks use a synchronous SQLAlchemy session (not async) — Celery does not support async natively
- `core/openai_client.py` provides `embed_texts(texts: list[str]) -> list[list[float]]` for batched embedding

## Status
complete

## Pending Tasks
None.

## Completion Notes
- Implemented as a **single orchestrating Celery task** (`extract_text`) that runs all four pipeline stages inline, avoiding large data passing through Redis.
- `app/processing/extractors.py`: per-format text extraction — PDF via `pdfplumber` (page-by-page), Markdown via regex strip, plain text via UTF-8 decode.
- `app/processing/chunker.py`: token-aware sliding-window chunker using `tiktoken` (cl100k_base). Preserves paragraph boundaries; falls back to hard token splits for long paragraphs. Raises `ValueError` if `overlap >= max_tokens`.
- `app/processing/tasks.py`: `_new_session()` factory is monkeypatchable for test isolation. `_db()` context manager handles rollback + close. `_mark_failed()` is called on any stage failure. Exponential retry backoff (up to 3 retries, capped at 600 s) with `throw=False` in tests to suppress Celery `Retry` propagation.
- `app/core/openai_client.py`: added sync `OpenAI` client and `embed_texts()` with `EMBEDDING_BATCH_SIZE=200` batching.
- `app/core/database.py`: added `SyncSessionLocal` (psycopg2 driver) for Celery workers.
- `app/core/config.py`: added `CHUNK_MAX_TOKENS=512`, `CHUNK_OVERLAP_TOKENS=50`, `EMBEDDING_BATCH_SIZE=200`.
- `requirements.txt`: added `psycopg2-binary>=2.9.10`.
- Alembic `005_add_document_processing_fields.py`: adds `chunk_count INTEGER NOT NULL DEFAULT 0` and `error_message TEXT` to `documents` table.
- Duplicate-run guard: task checks `doc.status == "processing"` and returns early — prevents concurrent duplicate jobs.
- Idempotency: `_stage_index` deletes all existing `DocumentChunk` rows for the document before inserting new ones.
- Tests: `tests/processing/test_chunker.py` (7 unit tests), `tests/processing/test_tasks.py` (8 integration tests covering happy path, idempotency, failure paths, and guard paths). Conftest uses distinct emails (`pipeline_owner@example.com`) to avoid unique-constraint collisions with other test modules.
- Design deviation: pipeline stages are not separate Celery tasks (spec suggested chaining). Single-task design chosen for simplicity and to avoid Redis serialization of large text/embedding payloads.
