# Conversations Component

## Purpose
Manages conversation sessions and message history. A conversation is a stateful interaction context that groups a series of user queries and system responses. Enables follow-up questions that build on prior context.

## Scope

### In Scope
- Create and manage conversation sessions
- Store messages (user queries + assistant responses) with citations
- Retrieve conversation history (paginated)
- List user's conversations
- Delete conversation

### Out of Scope
- Query execution and LLM response generation (owned by `query_engine`)
- Semantic search (owned by `retrieval`)

## Responsibilities
- Own `Conversation` and `Message` SQLAlchemy models
- CRUD for conversations (create, list, delete)
- Message persistence: write user message and assistant response after query completes
- Retrieve message history for a conversation (cursor-based pagination)
- Enforce ownership: users access only their own conversations

## Dependencies
- `auth` (get_current_user)
- `domains` (optional: validate domain_id if conversation is domain-scoped)
- `core/database.py`

## Related Models
- `Conversation`
- `Message`

## Related Endpoints
- `POST /api/v1/conversations` — create new conversation
- `GET /api/v1/conversations` — list user's conversations (paginated)
- `GET /api/v1/conversations/{conversation_id}` — get conversation detail
- `DELETE /api/v1/conversations/{conversation_id}` — delete conversation and messages
- `GET /api/v1/conversations/{conversation_id}/messages` — get message history (cursor-paginated)
- `POST /api/v1/conversations/{conversation_id}/query` — submit query (owned by `query_engine`, routed here)

## Business Rules
- A conversation belongs to exactly one user
- A conversation may optionally be scoped to a domain (domain_id nullable)
- Conversation scoping: if domain_id set, search is scoped to that domain for all queries in this conversation
- Message roles: `user` or `assistant`
- Messages are ordered by `created_at` (ascending) — oldest first
- Deleting a conversation hard-deletes all messages (no audit value in conversation history)
- Conversation title: auto-generated from first user message (first 60 chars) or user-provided

## Security Considerations
- Ownership check on every operation: `conversation.user_id == current_user.id`
- Return 404 (not 403) for conversations belonging to other users — prevent enumeration
- Citations stored as JSONB — no sensitive data; just document references

## Performance Considerations
- Message history: cursor-based pagination ordered by `created_at`
- Index on `(conversation_id, created_at)` ensures efficient cursor queries
- Conversation list: offset pagination, indexed on `user_id`
- Auto-generated title: derived in-memory from first query, not a DB computation

## Reliability Considerations
- Message persistence happens after query stream completes — not during streaming
- If message write fails after streaming: stream is already delivered to user; log the failure, return error to client, retry is safe
- Conversation delete cascades to messages at DB level (foreign key cascade)

## Testing Expectations
- Integration: create conversation → submit query → verify messages persisted
- Pagination: verify cursor-based pagination returns correct pages
- Permission: user cannot access another user's conversation
- Delete: conversation and messages removed; subsequent list does not include it
- Domain scoping: conversation with domain_id scopes queries correctly

## Implementation Notes
- `conversations/models.py`: `Conversation`, `Message` models
- `conversations/service.py`: `create_conversation()`, `list_conversations()`, `get_conversation_or_404()`, `delete_conversation()`, `get_messages()`, `append_message()`
- `conversations/schemas.py`: `ConversationResponse`, `MessageResponse`, `ConversationListResponse`
- Citations stored as `list[CitationSchema]` serialized into JSONB
- `CitationSchema`: `{ doc_id, doc_title, chunk_index, excerpt }` — defined in `shared/schemas.py`
- Cursor pagination: client passes `cursor` (last seen message ID), server returns messages after that ID

## Status
complete

## Pending Tasks
None.

## Completion Notes
- `app/conversations/models.py`: `Conversation` (user_id CASCADE, domain_id SET NULL nullable, title VARCHAR(255) nullable, timestamps) and `Message` (conversation_id CASCADE, role VARCHAR(16), content TEXT, citations JSONB nullable, created_at). Index on `(user_id)` for conversation list; composite index on `(conversation_id, created_at)` for cursor pagination.
- `app/conversations/schemas.py`: `ConversationCreateRequest` (optional title max 255, optional domain_id), `ConversationResponse` (from_attributes), `MessageResponse` with `from_orm_coerce()` classmethod that converts NULL citations to `[]` for consistent API shape, `MessagePageResponse` (messages list + next_cursor UUID|None).
- `app/conversations/service.py`: Full CRUD — `create_conversation` validates domain ownership before commit; `list_conversations` ordered by `updated_at DESC`; `get_conversation_or_404` returns 404 for foreign or missing conversations; `delete_conversation` hard-deletes (CASCADE handles messages); `get_messages` cursor pagination using `created_at > cursor_msg.created_at` with page_size+1 look-ahead, cursor validated for ownership to prevent cross-conversation cursor injection; `append_message` auto-generates title from first 60 chars of first user message if no title set, updates `conversation.updated_at`.
- `app/conversations/router.py`: POST (201), GET list (PaginatedResponse, offset-based), GET detail, DELETE, GET messages (ApiResponse with cursor data). Query engine's POST /{id}/query stub is intentionally absent — owned by query_engine component.
- `app/shared/schemas.py`: Added `CitationSchema` (doc_id, doc_title, chunk_index, excerpt).
- `alembic/versions/006_create_conversations.py`: Creates `conversations` and `messages` tables; revision `f6a7b8c9d0e1`, down_revision `e5f6a1b2c3d4`.
- `alembic/env.py` + `tests/conftest.py`: Imported `Conversation, Message` for migration autogenerate and test DB schema creation.
- `app/main.py`: `conversations_router` registered.
- Tests: `tests/conversations/conftest.py` (emails: `conv_owner@example.com`, `conv_other@example.com`; fixtures: user, domain, conversation, conversation_with_messages), `tests/conversations/test_service.py` (24 tests), `tests/conversations/test_router.py` (20 tests).
- Design decisions: domain_id uses SET NULL (conversations survive domain deletion); cursor validation rejects cross-conversation cursors with 404; title auto-generation skips whitespace-only content (strips first); assistant messages never trigger title generation.
