# Architecture Decisions — AtlasDB

## Architecture Style

**Modular monolith** with a separate Celery worker process.

Single FastAPI application with clear module boundaries. Celery workers run as a separate process (separate Docker container) but share the same codebase. No microservices split — the system does not have the team size or operational maturity to justify it.

## Module Structure

```
app/
  core/           # config, db session, security, dependencies
  auth/           # JWT auth logic
  users/          # user management
  domains/        # knowledge domain CRUD
  documents/      # file upload, metadata, status
  processing/     # Celery tasks: extract, chunk, embed, index
  retrieval/      # semantic search service
  conversations/  # conversation session management
  query_engine/   # context assembly, LLM call, streaming, citations
  shared/         # response schemas, exceptions, pagination
```

## API Design

- RESTful API
- All responses use unified shape: `{ "success": bool, "data": any, "message": str }`
- HTTP status codes are semantically correct and not replaced by `success` field
- Versioning: `/api/v1/` prefix
- Pagination on all list endpoints (offset-based for documents/domains, cursor-based for messages)

## Async Processing Model

Document upload is synchronous (file stored, DB record created, job enqueued). All heavy processing (extraction, chunking, embedding, indexing) runs asynchronously in Celery workers.

Pipeline is broken into discrete Celery tasks chained together:
```
extract_text → chunk_document → generate_embeddings → index_chunks
```

Each task is idempotent. Status tracked on the `Document` model: `pending → processing → indexed | failed`.

## Dependency Flow

```
auth → users → domains → documents → processing_pipeline
                                   ↓
                              retrieval ←── query_engine → conversations
```

## Streaming and Realtime Transport

SSE via FastAPI `StreamingResponse`. The query engine streams tokens from the OpenAI API and forwards them to the client. After streaming completes, the full response and citations are persisted to the conversation.

**Query cancellation** is supported via a separate REST endpoint (`DELETE /api/v1/conversations/{id}/query/{request_id}`) and a Redis-backed cancellation registry that the streaming generator polls between tokens. This provides bidirectional control without requiring WebSockets.

**Multi-device / live updates** (e.g. live conversation list, message arrival on a second device) are served, when added, by a secondary SSE channel — not WebSockets.

**WebSocket upgrade trigger**: the only foreseeable feature that would justify introducing WebSockets is true multi-user collaboration on a single conversation (concurrent participants seeing each other's input in real time). This is out of scope for the current build. If added later, a WebSocket endpoint will be introduced *alongside* SSE rather than replacing it — SSE remains the streaming transport for LLM responses.

## Vector Storage

pgvector extension on PostgreSQL. Vector embeddings stored in a `document_chunks` table with a `vector(1536)` column (for `text-embedding-3-small`). Similarity search uses cosine distance via `<=>` operator. IVFFlat index on the embeddings column.

## Error Handling

- HTTP errors return unified response with `success: false`
- Celery task failures update Document status to `failed` with error message stored
- LLM API failures return a graceful error response (no partial streaming)
- All errors logged with request context

## Reasoning

- Modular monolith chosen over microservices: simpler deployment, no network overhead between modules, easier debugging
- Celery chosen over RQ: mature retry/backoff, Flower monitoring UI, widely used in Python ecosystem
- pgvector chosen over dedicated vector DB (Pinecone, Weaviate): keeps infrastructure minimal, pgvector is production-ready for this scale, avoids extra service to manage
- SSE chosen over WebSockets: one-way data flow matches use case, simpler client integration, no connection state management. Bidirectional needs (cancellation, multi-device sync) are addressed via REST + secondary SSE channels rather than upgrading the transport.
