# Discovery Answers — AtlasDB

## Stack and Framework
- **Language**: Python 3.12+
- **Framework**: FastAPI
- **ORM**: SQLAlchemy (async) + Alembic for migrations
- **Source**: Defined in project brief

## Database
- **Primary**: PostgreSQL 16+
- **Vector extension**: pgvector
- **Source**: Defined in project brief

## Queue System
- **Decision**: Celery with Redis as broker and result backend
- **Why Celery over RQ**: More mature retry/backoff, better observability (Flower), broader ecosystem
- **Status**: Decided by BackendSmith — pending user confirmation (see open questions)

## Caching
- **Layer**: Redis
- **Use cases**: Celery broker/result backend; future: query result caching for frequent searches
- **Source**: Defined in project brief

## Auth
- **Type**: JWT (access token + refresh token)
- **Access token TTL**: 15 minutes
- **Refresh token TTL**: 7 days
- **Library**: `python-jose` or `PyJWT`
- **Decision**: BackendSmith — stateless, fits FastAPI perfectly

## User Roles
- **Open question**: Single role vs admin + regular user
- **Default assumption**: Two tiers (admin + user) — easier to add now than retrofit later
- See `13_open_questions.md`

## Multi-Tenancy / User Isolation
- **Open question**: Are users isolated from each other?
- **Default assumption**: User-owned isolation — each user sees only their own domains and documents
- See `13_open_questions.md`

## File Storage
- **Open question**: Local vs S3-compatible
- **Decision**: Abstracted storage interface. Local for dev. S3-compatible (boto3) for production. Config-driven via `STORAGE_BACKEND` env var.
- See `13_open_questions.md`

## Scale Expectations
- **Target**: hundreds of thousands of registered users (~100k–500k), tens of thousands of concurrent active sessions, thousands of concurrent in-flight queries at peak
- Millions of documents, tens of millions of chunks across the platform
- Horizontal scaling via stateless API replicas + Celery worker pools + Postgres read replicas + PgBouncer + Redis (shared cache / rate limiter / broker)
- See `08_performance_and_scaling.md` for detailed implications

## Streaming and Realtime Transport
- **Method**: FastAPI `StreamingResponse` with Server-Sent Events (SSE) format
- **Why SSE over WebSockets**: data flow is unidirectional (LLM tokens → client), simpler client integration, no persistent connection state to manage, works through standard HTTP infrastructure (LBs, proxies, CDNs) with zero special handling
- **Future bidirectional needs and how they are served without WebSockets**:
  - **Query cancellation** (stop generation mid-stream): served by `DELETE /api/v1/conversations/{id}/query/{request_id}` + Redis-backed cancellation registry checked by the streaming generator. Implemented in the initial build — see `query_engine` component.
  - **Live conversation list / multi-device sync**: served by a second SSE channel (`GET /api/v1/conversations/events`) or short polling. Not in the initial build, but the transport choice does not require WebSockets.
  - **Multi-user collaboration on a single conversation**: this is the only foreseeable feature that would require a true bidirectional channel. Out of scope. If this is added later, the upgrade path is to introduce a WebSocket endpoint *alongside* the existing SSE endpoint — SSE remains the primary transport for streaming responses.

## Testing
- **Expectations**: Unit tests for business logic, integration tests for critical flows (pipeline, RAG query), API tests for auth and permission boundaries
- **Not specified in brief — BackendSmith default**

## Deployment
- **Docker**: Yes, containerized — defined in brief
- **Workers**: Separate Celery worker container(s)
- **Source**: Defined in project brief
