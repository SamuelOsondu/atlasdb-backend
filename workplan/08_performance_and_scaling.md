# Performance and Scaling — AtlasDB

## Expected Scale (Assumptions)

- **Hundreds of thousands of registered users** (target: ~100k–500k)
- Tens of thousands of concurrent active sessions at peak
- Thousands of concurrent in-flight queries at peak
- Millions of documents across the platform; tens of millions of chunks total
- Per-user collections typically up to ~100k chunks; long-tail users may exceed this
- Query latency target: p50 < 2s to first token, p95 < 4s to first token
- Processing throughput: handle burst uploads, not real-time SLA — pipeline backlog acceptable up to minutes during peak

---

## Hot Paths and Concerns

### Query Path (user-facing, latency-sensitive)
1. Query embedding generation (OpenAI API call ~100ms)
2. pgvector similarity search (~10-50ms for <100k chunks with index)
3. Context assembly (in-memory, negligible)
4. LLM streaming (OpenAI, 1-10s — streamed so user sees progressive output)

**Key concern**: External API latency dominates. Minimize extra DB roundtrips in this path.

### Document Processing Pipeline (background, throughput-oriented)
1. Text extraction — CPU-bound, can be slow for large PDFs
2. Chunking — fast, CPU-bound
3. Embedding generation — I/O-bound (OpenAI API), batchable
4. Vector indexing — batch insert into pgvector

**Key concern**: Batch embeddings to minimize API calls. Chunk count per document can be large.

---

## N+1 Prevention

- Loading domain with document count: use SQL aggregation, not ORM lazy loading
- Loading conversations with message previews: single query with subquery or window function
- Chunk retrieval after vector search: single query with `IN` clause on chunk IDs

---

## Pagination

- All list endpoints paginated — no unbounded queries
- Document list: offset-based, default 20, max 100
- Message history: cursor-based (by `created_at`), default 50, max 200
- Search results: top-k only (no pagination — similarity search returns fixed k results)

---

## Async Processing Design

All heavy work runs in Celery workers:
- Text extraction (PDF parsing can be slow)
- Chunking (fast but should not block request cycle)
- Embedding generation (external API, batchable)
- Vector indexing (bulk insert)

API upload endpoint returns immediately after DB record created and job enqueued.
Pipeline status polled via `/documents/{id}` status endpoint.

---

## Embedding Batching

- OpenAI embeddings API supports batching up to 2048 inputs per request
- Chunk embeddings should be batched: collect all chunks for a document, embed in batches of 100-200 to balance latency and throughput
- Reduces API calls dramatically for large documents

---

## Vector Index

- **HNSW index** from day one given the 100k+ user target — IVFFlat does not hold up at multi-million chunk scale and rebuild cost is unacceptable in production
- HNSW parameters: `m = 16`, `ef_construction = 64` (tune via load testing)
- Cosine distance (`<=>`) for semantic similarity
- **Vector DB migration trigger**: when total chunk count crosses ~20M or pgvector p95 search latency exceeds 150ms under load, migrate to a dedicated vector store (Qdrant or Weaviate). The `retrieval` module's storage interface must be abstracted to make this swap mechanical.

---

## Caching Strategy

At hundreds-of-thousands-of-users scale, in-process caches are insufficient — caches must be Redis-backed and shared across API replicas.

- **Redis** is the canonical shared cache. Used for Celery broker/results, rate limiting state, query embedding cache, and (optionally) recent retrieval result cache.
- **Query embedding cache**: hash of normalized query text → embedding vector. Avoids redundant OpenAI embedding calls for repeated/popular queries. TTL ~24h.
- **User session / JWT denylist**: Redis-backed for revocation support across replicas.
- **Rate limiting**: must use Redis backend for `slowapi` (not in-process) — multiple API replicas otherwise allow N× the intended rate.
- **Future**: per-domain hot-chunk cache for frequently retrieved chunks (added based on profiling).

---

## Query Context Assembly

- Max 8 chunks per query (configurable via `MAX_CHUNKS_PER_QUERY`)
- Token counting via `tiktoken` before sending to LLM
- If 8 chunks exceed token budget, reduce to fit — prefer higher-ranked chunks
- Deduplication: skip chunks from the same document if highly overlapping

---

## Scaling Notes

- API is stateless — scale horizontally by adding uvicorn/gunicorn workers or API replicas behind a load balancer
- **SSE connection capacity**: each in-flight query holds an open HTTP connection for the duration of streaming (1–10s). At 10k concurrent queries that is 10k open connections — size uvicorn worker counts and OS file descriptor limits accordingly. Use ASGI servers tuned for high concurrent long-lived connections (uvicorn with `--workers` per CPU, `--limit-concurrency` set high).
- **Load balancer**: must support long-lived HTTP responses without idle timeout cutoff (SSE streams). Configure idle timeout ≥ 60s.
- **Database**:
  - Primary write node + read replicas from day one. Search/read queries route to replicas; writes (message persistence, document creation) go to primary.
  - PgBouncer (transaction pooling) in front of Postgres — at 100k+ users with hundreds of API workers, raw connection counts will exhaust Postgres without pooling.
  - Partition the `document_chunks` and `messages` tables by `user_id` hash (or by `created_at` for messages) once row counts exceed ~50M.
- **Celery workers** scale independently — separate worker pools for CPU-bound (extraction, chunking) vs I/O-bound (embedding API calls) work to avoid head-of-line blocking.
- **Celery broker**: Redis is acceptable up to mid-six-figure user counts; if broker becomes a bottleneck, move to RabbitMQ.
- **Object storage**: S3-compatible from day one — local filesystem cannot be shared across API replicas.
- **Observability**: distributed tracing (OpenTelemetry) is mandatory at this scale — without it, debugging cross-replica latency issues is intractable.
