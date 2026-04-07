# Documents Component

## Purpose
Manages document upload, metadata, lifecycle, and processing status. Entry point for all content that enters the knowledge base. Does not perform processing — it creates the record, stores the file, and enqueues the processing job.

## Scope

### In Scope
- File upload (PDF, Markdown, plain text)
- Document metadata management (title, type, domain association)
- Processing status tracking (`pending → processing → indexed | failed`)
- Document listing and filtering by domain
- Soft delete (marks document as deleted, excludes from search)
- Document reprocessing (admin: reset status, clear chunks, re-enqueue job)

### Out of Scope
- Text extraction, chunking, embedding (owned by `processing_pipeline`)
- Search/retrieval (owned by `retrieval`)
- Physical file deletion (deferred — soft delete preferred, hard delete only on explicit purge)

## Responsibilities
- Validate uploaded file type and size
- Store file via storage abstraction (`core/storage.py`)
- Create `Document` DB record with status `pending`
- Enqueue Celery processing job after record creation (post-commit)
- Expose status polling endpoint
- Enforce ownership: users manage only their own documents (via domain ownership)
- Soft delete: set `deleted_at`, exclude from all queries

## Dependencies
- `auth` (get_current_user)
- `domains` (get_domain_or_403 — verify user owns the target domain)
- `core/storage.py` (file storage)
- `processing_pipeline` (enqueue Celery task after upload)
- `core/database.py`

## Related Models
- `Document`
- `DocumentChunk` (read-only reference for chunk_count; chunks owned by processing)

## Related Endpoints
- `POST /api/v1/domains/{domain_id}/documents` — upload document to domain
- `GET /api/v1/domains/{domain_id}/documents` — list documents in domain (paginated)
- `GET /api/v1/documents/{document_id}` — get document detail + status
- `DELETE /api/v1/documents/{document_id}` — soft delete document
- `POST /api/v1/admin/documents/{document_id}/reprocess` — admin: reset and requeue processing

## Business Rules
- Supported file types: `pdf`, `md`, `txt`
- Max file size: configurable, default 50MB
- Document belongs to a domain; domain must be owned by the requesting user
- After upload, status is always `pending` — processing is async
- Soft-deleted documents must be excluded from all list endpoints and search
- A document in status `processing` cannot be deleted (return 409 Conflict)
- Reprocessing clears all existing chunks and resets status to `pending`
- Duplicate uploads (same filename in same domain) are allowed — each gets its own record

## Security Considerations
- File type validated by MIME type (not just extension) on upload
- File stored with UUID key — original filename is metadata only, never used in storage path
- Domain ownership verified before upload or listing
- Reprocessing endpoint is admin-only
- Deleted documents return 404 to non-admin users (not 410 — avoid information leak)

## Performance Considerations
- Large file uploads: use streaming multipart handling — do not load entire file into memory
- Document listing: paginated, indexed on `domain_id`, filtered by `deleted_at IS NULL`
- Status polling: single row fetch by `id` — fast

## Reliability Considerations
- File storage and DB record creation must succeed before Celery job is enqueued
- If Celery enqueue fails after DB write: document stays in `pending`, a background reconciliation or admin reprocess can recover it
- Never enqueue inside the DB transaction — enqueue after commit to avoid phantom jobs on rollback

## Testing Expectations
- Unit: file type validation, MIME checking
- Integration: upload flow — file stored, DB record created, job enqueued
- Permission: user cannot upload to another user's domain; user cannot delete another user's document
- Status: verify status transitions (pending → processing → indexed) via mock pipeline
- Soft delete: deleted doc returns 404, excluded from list
- Edge: file too large returns 413; unsupported type returns 422

## Implementation Notes
- `documents/models.py`: `Document` model
- `documents/service.py`: `upload_document()`, `get_document_or_404()`, `list_documents()`, `soft_delete_document()`, `reprocess_document()`
- Upload uses FastAPI `UploadFile` — stream to storage, then create DB record, then enqueue
- Status polling via `GET /documents/{id}` — no websocket needed
- `file_key` is the UUID-based storage path used by pipeline to retrieve file for processing

## Status
complete

## Pending Tasks
- None

## Completion Notes
- `app/core/exceptions.py`: `FileTooLargeError` added
- `app/core/config.py`: `MAX_FILE_SIZE_MB: int = 50` added
- `app/core/dependencies.py`: `get_storage_dep()` FastAPI dependency added for testable storage injection
- `app/documents/models.py`: `Document` model with soft-delete, denormalized `owner_id`, composite index on `(domain_id, deleted_at)`; `DocumentChunk` model with `Vector(1536)` embedding (nullable until processing runs)
- `app/documents/validation.py`: `validate_and_read_upload()` streams in 1MB chunks, MIME validation with extension fallback for generic content-types
- `app/documents/schemas.py`: `DocumentResponse` (full detail with `file_key`), `DocumentListResponse` (list view, no `file_key`), both with `from_attributes=True`; `chunk_count` defaults to 0
- `app/documents/service.py`: `upload_document`, `get_document_or_404`, `get_any_document_or_404`, `list_documents`, `soft_delete_document`, `reprocess_document`, `count_document_chunks`; Celery enqueue deferred import (`enqueue_processing`); commit-before-enqueue pattern enforced
- `app/documents/router.py`: 4 endpoints — POST upload (multipart), GET list (paginated), GET detail, DELETE soft-delete
- `app/admin/documents_router.py`: POST reprocess admin endpoint with `require_admin`
- `alembic/versions/004_create_documents.py`: raw DDL for `document_chunks` table with `vector(1536)` column; HNSW index (m=16, ef_construction=64)
- `app/main.py`: `FileTooLargeError` → 413 handler; documents + admin_documents routers registered
- `alembic/env.py`: `Document`, `DocumentChunk` imports added
- `tests/conftest.py`: pgvector extension created before `create_all`; `Document`, `DocumentChunk` imports added
- Tests: `tests/documents/conftest.py` (fixtures: user_with_token, other_user_with_token, admin_user_with_token, domain, document, indexed_document, processing_document, InMemoryStorage); `test_service.py` (17 tests); `test_router.py` (21 tests)
