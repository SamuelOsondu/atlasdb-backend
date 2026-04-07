# Agent Directive — AtlasDB

## Project Intent

AtlasDB is a production-grade RAG (Retrieval-Augmented Generation) backend. It ingests organizational documents, processes them asynchronously through a chunking and embedding pipeline, and serves grounded, citation-backed answers to natural language queries via a FastAPI REST API.

## Non-Negotiable Rules

- Never write code outside of a component's defined scope
- All list endpoints must be paginated — no unbounded queries
- All LLM-generated responses must include citations referencing chunk source
- Document processing is always async — never block a request for pipeline work
- JWT auth is required on all endpoints except `/auth/register` and `/auth/login`
- Response format is always `{ "success": bool, "data": any, "message": str }`
- Celery tasks must be idempotent — safe to retry without double-processing
- Do not change stack or introduce new dependencies without updating this workplan
- Soft delete documents via `deleted_at`; hard delete chunks (they are regeneratable)
- All secrets are loaded from environment variables — never hardcoded

## How to Resume Work

1. Read this file
2. Read `01_project_summary.md`
3. Read `03_architecture_decisions.md`
4. Check `12_progress_tracker.md`
5. Read the target component file in `components/`
6. Proceed with implementation

## Current Phase

Planning complete. Ready for implementation.
