# Testing Strategy — AtlasDB

## Philosophy

Tests reflect real risk. Critical paths must be covered. Derived/regeneratable logic (chunking algorithms) needs lighter coverage than ownership rules and pipeline state transitions.

## Test Types

### Unit Tests
Target: isolated business logic with no external dependencies

- Chunking algorithm (chunk boundaries, token limits, overlap)
- Context assembly (token budget enforcement, chunk selection, deduplication)
- JWT generation and validation
- Password hashing/verification
- Citation extraction from LLM response

### Integration Tests
Target: service-layer flows with real DB (test PostgreSQL instance)

- Full document processing pipeline (mock OpenAI, real DB)
- Semantic search returning correct chunks
- Conversation message persistence after RAG query
- Soft delete behavior (deleted docs excluded from search)
- Ownership enforcement (user cannot access another user's domain)

### API Tests
Target: HTTP contract verification

- Auth flow: register → login → refresh → protected endpoint
- Unauthorized access returns 401
- Document upload returns 202 with processing status
- Search endpoint returns ranked results
- Query endpoint streams response (verify SSE format)
- Pagination parameters respected

### Permission Tests
Target: authorization boundaries

- User cannot access another user's domain
- User cannot query documents in a domain they do not own
- Admin-only endpoints reject non-admin users
- Deleted document chunks not returned in search

### Failure Path Tests
Target: error handling under adverse conditions

- OpenAI API error during embedding generation → task marked failed
- OpenAI API error during LLM query → graceful 503 response
- Unsupported file type upload → 422 validation error
- Invalid JWT → 401
- Expired access token → 401 (with refresh token hint)

## Critical Flows (Must Cover)

1. Full registration → login → upload document → wait for processing → query → get cited response
2. Soft delete document → search no longer returns its chunks
3. Celery task failure → document status set to `failed`
4. Rate limit exceeded on query endpoint → 429 response

## Test Infrastructure

- Framework: `pytest` + `pytest-asyncio`
- HTTP test client: `httpx` (async) via FastAPI `TestClient`
- Test DB: separate PostgreSQL database with pgvector (not mocked)
- OpenAI: mocked in all tests using `unittest.mock.patch` or `pytest-mock`
- Celery: tasks called synchronously in tests (`CELERY_TASK_ALWAYS_EAGER=True`)
- Fixtures: defined in `tests/conftest.py`
  - `db_session` — async test DB session
  - `test_user` — seeded user with auth token
  - `test_domain` — seeded knowledge domain
  - `test_document` — seeded indexed document with chunks

## Coverage Expectations

- Auth module: high coverage (security-critical)
- Ownership checks: full coverage
- Pipeline state transitions: full coverage
- Chunking/embedding logic: unit test coverage
- LLM prompt construction: unit test (verify grounding instructions present)
- Streaming: basic integration test (verify SSE format)
