# Project Summary — AtlasDB

## Product Description

AtlasDB is an intelligent knowledge retrieval backend. It transforms unstructured organizational documents into a structured, semantically searchable knowledge base. It supports natural language queries and returns grounded answers with citations derived directly from indexed document sources.

## Actors

- **Authenticated User**: Can manage knowledge domains, upload and manage documents, run semantic searches, create conversations, and ask follow-up questions.
- **Admin** (open question — see `13_open_questions.md`): May have elevated access to manage all users, force reprocessing, view system health.

## Core Flows

### 1. Document Ingestion
User uploads a file → System stores file (file storage backend) → Creates Document record with status `pending` → Enqueues async processing job

### 2. Document Processing Pipeline (async via Celery)
Text extraction → Content chunking → Embedding generation (OpenAI) → pgvector indexing → Document status updated to `indexed`

Failure at any stage: task retries with exponential backoff (max 3 attempts); status set to `failed` after exhaustion

### 3. Semantic Search
User submits query (optionally scoped to a domain) → Query embedded via OpenAI → pgvector similarity search → Ranked chunks returned with metadata

### 4. Conversational Query (RAG)
User submits query in a conversation session → Retrieve top-k chunks via semantic search → Assemble context (max 8 chunks, ~6000 tokens) → Send to LLM with grounding prompt → Stream response with citations → Persist message + response to conversation history

### 5. Conversation History
User retrieves messages in a conversation — paginated, ordered by creation time

## Business Rules

- Documents belong to a knowledge domain
- Queries may be scoped to a domain or cross-domain (domain_id optional)
- Responses must only use provided context — no hallucination
- Every response must include citations: document title, doc ID, chunk position, excerpt
- Processing stages are independent — failure in chunking does not corrupt already-extracted text
- Soft-deleted documents are excluded from search and retrieval
- Token budget for context: max ~6000 tokens (leaves room for system prompt + response in 128k model window)
- Conversation state allows follow-up questions to reference prior messages

## System Boundaries

**In scope:**
- Auth (JWT)
- Knowledge domain management
- Document upload, management, status tracking
- Async processing pipeline (extract, chunk, embed, index)
- Semantic search
- Conversational RAG with streaming
- Citation-backed responses
- Conversation history

**Out of scope:**
- Fine-tuning or custom model hosting
- Real-time collaboration
- User-facing frontend
- Analytics dashboard
- Document version control

## Assumptions

- File storage uses a configurable backend: local filesystem for dev, S3-compatible for production
- Users are isolated (each user owns their domains and documents) — pending confirmation
- Queue: Celery with Redis broker
- Embedding model: `text-embedding-3-small`
- LLM: `gpt-4o-mini` (configurable via env)
