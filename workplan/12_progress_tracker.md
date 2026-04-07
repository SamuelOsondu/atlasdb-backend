# Progress Tracker — AtlasDB

## Current Phase

**Implementation complete — all components implemented.**

## Last Updated

2026-04-07

## Current Focus

All components complete. Backend implementation finished.

## Component Status

| Component | Status | Notes |
|---|---|---|
| auth | complete | JWT register/login/refresh/logout, token rotation, rate limiting |
| users | complete | Profile read/update, password change, admin list/deactivate/reactivate |
| domains | complete | KnowledgeDomain CRUD, ownership enforcement, cascade soft-delete |
| documents | complete | File upload, metadata, status tracking, soft delete, admin reprocess |
| processing_pipeline | complete | Single Celery task: extract → chunk → embed → index; sync session; retry backoff |
| retrieval | complete | POST /search; pgvector cosine similarity; ownership + soft-delete SQL filters; 503 on embed failure |
| conversations | complete | Conversation + Message models; cursor pagination; auto-title; domain scoping |
| query_engine | complete | SSE streaming, context assembly, citations, Redis cancellation, rate limiting |

## Workplan Status

| File | Status |
|---|---|
| 00_agent_directive.md | complete |
| 01_project_summary.md | complete |
| 02_discovery_answers.md | complete |
| 03_architecture_decisions.md | complete |
| 04_stack_and_infra.md | complete |
| 05_api_integrations.md | complete |
| 06_data_and_schema_strategy.md | complete |
| 07_security_and_risk.md | complete |
| 08_performance_and_scaling.md | complete |
| 09_coding_standards.md | complete |
| 10_testing_strategy.md | complete |
| 11_component_index.md | complete |
| 12_progress_tracker.md | complete |
| 13_open_questions.md | complete |
| 14_runbook_notes.md | complete |

## Completed

- Project scaffold: `Dockerfile`, `docker-compose.yml`, `requirements.txt`, `.env.example`, `.gitignore`, `pytest.ini`
- `app/core/`: `config`, `database`, `security`, `exceptions`, `rate_limit`, `storage`, `openai_client`, `dependencies`
- `app/shared/`: `schemas` (ApiResponse, PaginatedResponse), `enums` (DocumentStatus, MessageRole)
- `app/users/models.py`: User model (required by auth)
- `app/auth/`: `models` (RefreshToken), `schemas`, `service`, `router`
- `app/main.py`, `app/celery_app.py`
- Alembic: `alembic.ini`, `env.py`, migrations `001` (pgvector) and `002` (users + refresh_tokens)
- Tests: `tests/conftest.py`, `tests/auth/test_service.py`, `tests/auth/test_router.py`
- `app/users/`: `schemas`, `service`, `router`
- `app/admin/users_router.py`: admin list/deactivate/reactivate
- `app/core/dependencies.py`: `require_admin` + `get_storage_dep` added
- Auth fix: inactive account login raises `ForbiddenError` → 403
- Tests: `tests/users/conftest.py`, `tests/users/test_service.py`, `tests/users/test_router.py`
- `app/domains/`: `models` (UniqueConstraint owner+name), `schemas`, `service` (get_domain_or_404, cascade soft-delete), `router`
- `alembic/versions/003_create_knowledge_domains.py`
- Tests: `tests/domains/conftest.py`, `tests/domains/test_service.py`, `tests/domains/test_router.py`
- `app/core/exceptions.py`: `FileTooLargeError` added
- `app/core/config.py`: `MAX_FILE_SIZE_MB: int = 50` added
- `app/documents/`: `models` (Document + DocumentChunk with Vector(1536)), `validation` (MIME + size), `schemas`, `service`, `router`
- `app/admin/documents_router.py`: admin reprocess endpoint
- `alembic/versions/004_create_documents.py`: documents + document_chunks tables, HNSW index
- `app/main.py`: `FileTooLargeError` → 413 handler; documents routers registered
- `tests/conftest.py`: pgvector extension created before `create_all`
- Tests: `tests/documents/conftest.py`, `tests/documents/test_service.py`, `tests/documents/test_router.py`
- `app/core/config.py`: `CHUNK_MAX_TOKENS`, `CHUNK_OVERLAP_TOKENS`, `EMBEDDING_BATCH_SIZE` added
- `app/core/database.py`: `SyncSessionLocal` (psycopg2) for Celery workers
- `app/core/openai_client.py`: sync `embed_texts()` with batching
- `app/processing/`: `extractors.py` (PDF/MD/TXT), `chunker.py` (tiktoken sliding window), `tasks.py` (orchestrating Celery task)
- `alembic/versions/005_add_document_processing_fields.py`: `chunk_count` + `error_message` columns
- `requirements.txt`: `psycopg2-binary>=2.9.10`
- Tests: `tests/processing/conftest.py`, `tests/processing/test_chunker.py`, `tests/processing/test_tasks.py`
- `app/core/config.py`: `MIN_SIMILARITY_SCORE: float = 0.7` added
- `app/core/exceptions.py`: `ServiceUnavailableError` added
- `app/core/openai_client.py`: `async_embed_text()` added
- `app/retrieval/`: `__init__.py`, `schemas.py`, `service.py`, `router.py`
- `app/main.py`: `retrieval_router` registered; `ServiceUnavailableError` → 503 handler added
- Tests: `tests/retrieval/conftest.py`, `tests/retrieval/test_service.py`, `tests/retrieval/test_router.py`
- `app/shared/schemas.py`: `CitationSchema` added
- `app/conversations/`: `__init__.py`, `models.py`, `schemas.py`, `service.py`, `router.py`
- `alembic/versions/006_create_conversations.py`: `conversations` + `messages` tables
- `alembic/env.py` + `tests/conftest.py`: Conversation, Message model imports added
- `app/main.py`: `conversations_router` registered
- Tests: `tests/conversations/conftest.py`, `tests/conversations/test_service.py`, `tests/conversations/test_router.py`
- `app/core/config.py`: `CONTEXT_TOKEN_BUDGET: int = 6000`, `CONVERSATION_HISTORY_MESSAGES: int = 12` added
- `app/core/redis_client.py`: async Redis singleton (`get_redis()`) using `redis.asyncio`
- `app/core/openai_client.py`: `stream_chat_completion(messages) -> AsyncGenerator[str, None]` added
- `app/query_engine/`: `__init__.py`, `schemas.py`, `prompts.py`, `context.py`, `service.py`, `router.py`
- `app/main.py`: `query_engine_router` registered
- `requirements.txt`: `redis[asyncio]>=5.0.0` added
- Tests: `tests/query_engine/conftest.py`, `tests/query_engine/test_context.py` (16 tests), `tests/query_engine/test_prompts.py` (6 tests), `tests/query_engine/test_service.py` (14 tests), `tests/query_engine/test_router.py` (13 tests)

## Next Steps

All components complete. No further implementation steps.
