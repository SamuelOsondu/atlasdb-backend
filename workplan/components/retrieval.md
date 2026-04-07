# Retrieval Component

## Purpose
Provides semantic search over the indexed knowledge base. Accepts a natural language query, generates a query embedding, performs pgvector cosine similarity search, and returns a ranked list of relevant document chunks with metadata. Used both directly (search endpoint) and internally by the query engine for RAG.

## Scope

### In Scope
- Query embedding generation via OpenAI
- pgvector cosine similarity search
- Filtering by domain (optional) and ownership
- Metadata filtering (file type, domain — future)
- Ranked result schema with chunk content, score, and source metadata
- Exclusion of soft-deleted documents from results

### Out of Scope
- LLM response generation (owned by `query_engine`)
- Context assembly (owned by `query_engine`)
- Conversation management (owned by `conversations`)

## Responsibilities
- Accept a search query and optional `domain_id` scoping parameter
- Generate query embedding via OpenAI `text-embedding-3-small`
- Perform similarity search using pgvector `<=>` cosine distance operator
- Filter results to only include chunks from non-deleted documents owned by the requesting user
- Return top-k results (default k=10 for search endpoint, configurable)
- Include in each result: chunk content, chunk index, source document ID, document title, domain ID, similarity score

## Dependencies
- `auth` (get_current_user)
- `core/openai_client.py` (embed query)
- `core/database.py`
- `documents` models (join to filter by ownership and deleted_at)
- `domains` (ownership check for domain-scoped search)

## Related Models
- `DocumentChunk` (primary search target)
- `Document` (join for ownership + soft delete filter)
- `KnowledgeDomain` (join for ownership validation)

## Related Endpoints
- `POST /api/v1/search` — semantic search (user-facing)

Internal service method (not an HTTP endpoint):
- `retrieval_service.search(query, user_id, domain_id, top_k)` — called by query engine

## Business Rules
- Results are always filtered to chunks where parent document is not soft-deleted
- Results are always filtered to chunks owned by the requesting user (via domain → user chain)
- Domain scoping: if `domain_id` provided, restrict search to that domain (verify ownership first)
- If no `domain_id` provided, search across all of the user's indexed documents
- Minimum similarity score threshold: configurable (default 0.7) — discard irrelevant results below threshold
- Top-k: 10 for search endpoint, 8 for RAG context (configurable via `MAX_CHUNKS_PER_QUERY`)
- If fewer results than k meet the threshold, return only qualifying results

## Security Considerations
- Ownership enforced via SQL JOIN — not application-level filtering after fetch
- SQL query uses parameterized inputs — no injection risk
- `domain_id` validated as belonging to current user before search if provided
- Similarity scores not sensitive but should not expose chunk content from unauthorized documents

## Performance Considerations
- IVFFlat index on `document_chunks.embedding` is critical — ensure it exists before search operations
- Ownership filter applied in the same SQL query as vector search (via JOIN + WHERE) — not a post-filter
- Query embedding generation (~100ms) is the first bottleneck — consider caching for identical queries (future)
- Top-k should be small (≤20) to keep vector search fast
- Result set is fixed-size — no pagination on search results

## Reliability Considerations
- OpenAI embedding failure: return 503 with clear error message to user
- pgvector search failure: return 503
- Empty result is a valid outcome — return empty array with `success: true`

## Testing Expectations
- Integration: upload + index a document → search → verify correct chunk returned
- Permission: search does not return chunks from another user's documents
- Domain scoping: search with `domain_id` returns only that domain's chunks
- Soft delete: deleted document chunks not returned in results
- Threshold: low-relevance chunks filtered out
- Empty: search with no indexed documents returns empty results (not error)

## Implementation Notes
- `retrieval/service.py`: `search(query: str, user_id: UUID, domain_id: UUID | None, top_k: int) -> list[SearchResult]`
- SQL pattern:
  ```sql
  SELECT dc.id, dc.content, dc.chunk_index, dc.metadata,
         d.id as doc_id, d.title, d.domain_id,
         1 - (dc.embedding <=> :query_embedding) as score
  FROM document_chunks dc
  JOIN documents d ON dc.document_id = d.id
  JOIN knowledge_domains kd ON d.domain_id = kd.id
  WHERE kd.owner_id = :user_id
    AND d.deleted_at IS NULL
    AND (kd.id = :domain_id OR :domain_id IS NULL)
    AND 1 - (dc.embedding <=> :query_embedding) >= :threshold
  ORDER BY dc.embedding <=> :query_embedding
  LIMIT :top_k
  ```
- `retrieval/schemas.py`: `SearchRequest`, `SearchResult`, `SearchResponse`
- `retrieval/router.py`: `POST /search` — thin, delegates to service

## Status
complete

## Pending Tasks
None.

## Completion Notes
- `app/retrieval/schemas.py`: `SearchRequest` (query, optional domain_id, top_k 1–50), `SearchResult` (chunk_id, document_id, domain_id, document_title, chunk_index, text, score), `SearchResponse` (results + total).
- `app/retrieval/service.py`: `search(query, user_id, domain_id, top_k, db, threshold)` async function. Domain ownership verified via `get_domain_or_404` before any DB query. Query embedding generated via `async_embed_text` (wrapped in `ServiceUnavailableError` on failure). pgvector cosine similarity search implemented with raw SQL using `(:query_embedding)::vector` cast and `<=>` operator. Ownership enforced at SQL JOIN level (`kd.owner_id = :user_id`). Soft-delete filter applied inline (`d.deleted_at IS NULL`). NULL embeddings skipped (`dc.embedding IS NOT NULL`). Threshold applied in WHERE clause. `domain_id` filter added conditionally to avoid asyncpg NULL UUID type inference issues. `threshold` parameter defaults to `settings.MIN_SIMILARITY_SCORE` but can be overridden by query engine callers.
- `app/retrieval/router.py`: `POST /api/v1/search` — auth required, delegates to service, returns `ApiResponse` wrapping `SearchResponse`.
- `app/core/exceptions.py`: Added `ServiceUnavailableError` → 503 handler in main.py.
- `app/core/config.py`: Added `MIN_SIMILARITY_SCORE: float = 0.7`.
- `app/core/openai_client.py`: Added `async_embed_text(text: str) -> list[float]` (async, single-query, uses AsyncOpenAI client).
- `app/main.py`: Registered `retrieval_router`, imported and handled `ServiceUnavailableError` → 503.
- Tests: `tests/retrieval/conftest.py` (unique emails: `search_owner@example.com`, `search_other@example.com`; deterministic 1536-dim unit vectors `MATCH_EMBEDDING` / `ORTHO_EMBEDDING`; user/domain/document/chunk fixtures), `tests/retrieval/test_service.py` (12 tests), `tests/retrieval/test_router.py` (12 tests).
- Test coverage: happy path, metadata correctness, ordering, empty results, ownership isolation, domain scoping, soft-delete exclusion, threshold filtering (high and zero), top_k limiting, embedding failure → ServiceUnavailableError, NULL embedding exclusion, HTTP auth/validation errors (401, 422, 404, 503).
