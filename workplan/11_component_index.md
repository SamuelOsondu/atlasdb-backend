# Component Index — AtlasDB

## Components

| Component | File | Purpose | Status |
|---|---|---|---|
| Auth | components/auth.md | JWT registration, login, token refresh | complete |
| Users | components/users.md | User profile management | complete |
| Domains | components/domains.md | Knowledge domain CRUD | complete |
| Documents | components/documents.md | File upload, metadata, status tracking | not_started |
| Processing Pipeline | components/processing_pipeline.md | Async Celery pipeline: extract, chunk, embed, index | not_started |
| Retrieval | components/retrieval.md | Semantic search via pgvector | not_started |
| Conversations | components/conversations.md | Conversation session and message history | not_started |
| Query Engine | components/query_engine.md | Context assembly, LLM call, streaming, citations | not_started |

## Dependency Order (Implementation Sequence)

```
1. auth          — no internal deps
2. users         — depends on auth
3. domains       — depends on users
4. documents     — depends on domains
5. processing    — depends on documents + retrieval (vector write)
6. retrieval     — depends on documents (reads chunks)
7. conversations — depends on users + domains
8. query_engine  — depends on retrieval + conversations
```

## Ownership Boundaries

- **auth** owns: JWT issuance, refresh, revocation, password verification
- **users** owns: User model, profile reads/updates
- **domains** owns: KnowledgeDomain model, ownership enforcement
- **documents** owns: Document model, file storage, upload lifecycle, status tracking
- **processing** owns: Celery tasks, DocumentChunk creation, embedding generation, vector writes
- **retrieval** owns: pgvector search, ranking, search result schemas
- **conversations** owns: Conversation + Message models, history persistence
- **query_engine** owns: context assembly, LLM call, streaming, citation extraction, response persistence
