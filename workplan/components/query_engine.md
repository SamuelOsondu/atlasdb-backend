# Query Engine Component

## Purpose
Orchestrates the full RAG pipeline for a user query: retrieves relevant document chunks, assembles a context-bounded prompt, calls the LLM with streaming enabled, streams the response to the client via SSE, extracts citations, and persists the exchange to the conversation.

## Scope

### In Scope
- Accept a query within a conversation context
- Call retrieval service to get top-k relevant chunks
- Assemble context from retrieved chunks (token budget management)
- Construct system prompt with grounding instructions
- Call OpenAI chat completions API with streaming
- Stream LLM response tokens to client via SSE
- Extract citations from retrieved chunks used in context
- Persist user message + assistant response + citations to conversation after streaming
- Rate limiting on this endpoint
- **Query cancellation**: client-initiated stop of an in-flight streaming response via a separate REST endpoint, propagated through a Redis-backed cancellation registry

### Out of Scope
- Vector search (owned by `retrieval`)
- Message storage model (owned by `conversations`)
- File processing (owned by `processing_pipeline`)

## Responsibilities
- Validate conversation ownership before processing query
- Load recent conversation history (last N messages) for context continuity
- Call `retrieval_service.search()` with the user's query
- Assemble context: select top chunks within token budget, deduplicate overlapping content
- Count tokens via `tiktoken` to enforce context window limits
- Build system prompt from `query_engine/prompts.py`
- Call OpenAI `chat.completions.create(stream=True)` with assembled context + conversation history
- Yield SSE events as tokens arrive
- After stream completion: extract citations from used chunks, persist messages to DB
- Apply rate limiting: 10 requests/minute per user

## Dependencies
- `auth` (get_current_user)
- `conversations` (get_conversation_or_404, append_message)
- `retrieval` (search service)
- `core/openai_client.py` (streaming LLM call)
- `core/database.py`
- External: OpenAI API

## Related Models
- `Conversation` (read — verify ownership, get domain_id)
- `Message` (write — persist user query + assistant response)

## Related Endpoints
- `POST /api/v1/conversations/{conversation_id}/query` — submit query, stream response. Response includes a `request_id` in the first SSE event.
- `DELETE /api/v1/conversations/{conversation_id}/query/{request_id}` — cancel an in-flight query. Sets a cancellation flag in Redis; the streaming generator polls between tokens and terminates the stream cleanly with a `cancelled: true` final event. No partial response is persisted.

## Business Rules
- Conversation must belong to requesting user
- Context window budget: max 6000 tokens for retrieved chunks (leaves space for system prompt + history + response in 128k model window)
- Max chunks in context: `MAX_CHUNKS_PER_QUERY` (default 8) — prefer higher-ranked chunks when budget exceeded
- Conversation history: include last 6 message pairs (user + assistant) for follow-up continuity
- Grounding rule: system prompt must instruct LLM to use only provided context; no unsupported claims
- If no relevant chunks found (all below similarity threshold): respond with "no relevant documents found" message — do not hallucinate
- Citations: include all chunks actually passed to LLM as context (not just top-1)
- Response must always include citation references, even if LLM does not explicitly quote them
- User message + assistant response persisted atomically after streaming completes

## Security Considerations
- Conversation ownership check before any processing
- Rate limiting: 10 queries/minute per user (`slowapi`)
- OpenAI API key in env only — not logged, not exposed
- Prompt injection: system prompt is pre-pended before any user content; user query is clearly labeled; chunks are labeled with source identifiers
- Do not include chunk content in error responses (could leak data on unexpected errors)

## Performance Considerations
- Streaming via SSE: first token displayed to user ~1-2s after request (embedding + vector search + LLM TTFT)
- Token counting via `tiktoken` is fast (in-memory)
- Context assembly is in-memory — no additional DB calls beyond initial chunk retrieval
- Message persistence happens after stream completes — does not block the stream
- Keep conversation history query lean: fetch only role + content of last N messages

## Reliability Considerations
- If OpenAI API fails during streaming mid-response: close SSE stream with an error event; do not persist partial response
- If message persistence fails after streaming: log error, send error event to client — stream already delivered; idempotent retry via client resubmit
- Rate limit exceeded: return 429 before any LLM call is made

## Testing Expectations
- Unit: context assembly (token budget enforcement, chunk selection, deduplication)
- Unit: prompt construction (verify grounding instructions present)
- Unit: citation extraction from chunks
- Integration: full query flow with mock OpenAI (mock streaming response) — verify messages persisted, citations present
- Permission: query in another user's conversation returns 404
- Empty retrieval: query with no relevant chunks returns appropriate no-results message
- Rate limit: 11th request in a minute returns 429
- Stream format: verify SSE event format (data: {token}\n\n)

## Implementation Notes

### SSE Format
```
data: {"token": "Hello"}\n\n
data: {"token": " world"}\n\n
data: {"done": true, "citations": [...]}\n\n
```

### Context Assembly
```python
def assemble_context(chunks: list[SearchResult], max_tokens: int) -> tuple[str, list[Citation]]:
    selected = []
    token_count = 0
    for chunk in chunks:  # already ranked by score
        chunk_tokens = count_tokens(chunk.content)
        if token_count + chunk_tokens > max_tokens:
            break
        selected.append(chunk)
        token_count += chunk_tokens
    return format_context(selected), extract_citations(selected)
```

### System Prompt Structure
```
You are a knowledge assistant. Answer using ONLY the provided context.
If the context does not contain the answer, say so explicitly.
Do not make up information.

Context:
[SOURCE 1: {doc_title}]
{chunk_content}

[SOURCE 2: {doc_title}]
{chunk_content}
...
```

- `query_engine/service.py`: `handle_query(conversation_id, query, user)` — orchestration
- `query_engine/streaming.py`: async generator that yields SSE-formatted strings
- `query_engine/prompts.py`: system prompt templates
- `query_engine/schemas.py`: `QueryRequest`, `CitationSchema`
- Router uses `StreamingResponse` with `media_type="text/event-stream"`

## Status
complete

## Pending Tasks
None.

## Completion Notes
- `app/core/config.py`: Added `CONTEXT_TOKEN_BUDGET: int = 6000` and `CONVERSATION_HISTORY_MESSAGES: int = 12`.
- `app/core/redis_client.py`: Async Redis singleton (`get_redis()`) backed by `redis.asyncio`. Lazy-initialised; connection pool managed by redis-py.
- `app/core/openai_client.py`: Added `stream_chat_completion(messages) -> AsyncGenerator[str, None]` — async generator yielding token strings from `chat.completions.create(stream=True)`.
- `app/query_engine/__init__.py`: Empty package marker.
- `app/query_engine/schemas.py`: `QueryRequest(query: str Field(min_length=1, max_length=4000))`.
- `app/query_engine/prompts.py`: `build_system_prompt(context_text)` — interpolates pre-formatted context into grounding prompt template that instructs LLM to answer from context only.
- `app/query_engine/context.py`: `count_tokens(text)` (tiktoken cl100k_base), `format_context(chunks)` (numbered SOURCE labels), `assemble_context(chunks, max_tokens)` (greedy fill, highest-ranked first), `extract_citations(chunks)` (doc_id str, doc_title, chunk_index, excerpt[:200]).
- `app/query_engine/service.py`: `handle_query(conversation, query, request_id, user_id, db, redis_client)` async generator. Flow: yield request_id → search() → empty-check → assemble_context → _get_recent_history → build LLM messages → stream tokens (poll Redis cancel key between tokens) → yield done+citations → persist user+assistant messages. Cancellation and error paths do not persist messages.
- `app/query_engine/router.py`: `POST /conversations/{id}/query` (StreamingResponse, text/event-stream, rate-limited 10/min per user via `_get_user_key` JWT extraction); `DELETE /conversations/{id}/query/{request_id}` (sets `cancel:{request_id}` TTL 300s in Redis, idempotent). Both endpoints enforce conversation ownership via `get_conversation_or_404`.
- `app/main.py`: `query_engine_router` registered.
- `requirements.txt`: Added `redis[asyncio]>=5.0.0`.
- Tests: `tests/query_engine/__init__.py`, `tests/query_engine/conftest.py` (emails: `qe_owner@example.com`, `qe_other@example.com`; `FakeRedis` stub; `SAMPLE_CHUNKS`; fixtures: user, other_user, domain, conversation, conversation_in_domain, fake_redis), `tests/query_engine/test_context.py` (16 unit tests), `tests/query_engine/test_prompts.py` (6 unit tests), `tests/query_engine/test_service.py` (14 integration tests with monkeypatched search + stream), `tests/query_engine/test_router.py` (13 HTTP tests).
- Design decisions: Redis cancel key polled between every LLM token (EXISTS call); partial/cancelled responses never persisted; no-results path streams a single explanatory token then done with empty citations; `_get_recent_history` fetches last N rows DESC then reverses in Python for chronological ordering.
