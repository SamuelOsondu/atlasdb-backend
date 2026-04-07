# Security and Risk — AtlasDB

## Risk Profile

**Medium risk.** No money movement. Key risks: unauthorized access to organizational knowledge, LLM API cost abuse, pipeline resource exhaustion, prompt injection via document content.

---

## Authentication

- JWT with short-lived access tokens (15 min) and longer-lived refresh tokens (7 days)
- Refresh tokens hashed before storage; revocation supported via DB flag
- Passwords hashed with bcrypt (min cost factor 12)
- No password in any response payload, ever
- `/auth/register` and `/auth/login` are the only unauthenticated endpoints

## Authorization

- All endpoints require a valid access token
- Ownership enforced at service layer: users can only access their own domains, documents, conversations
- Admin role (`is_admin`) gates admin-only endpoints
- Authorization check must happen in service logic, not just route decorators (defense in depth)
- Domain ownership validated before any document or search operation

## Sensitive Operations

| Operation | Protection |
|---|---|
| Document upload | Auth + ownership check + file type validation |
| Semantic search | Auth + domain ownership check |
| LLM query | Auth + rate limiting + token budget enforcement |
| Conversation access | Auth + ownership check |
| Admin endpoints | Auth + `is_admin` check |
| Refresh token exchange | Token hash comparison + expiry + revocation check |

## Input Validation

- All request bodies validated via Pydantic schemas
- File uploads: validate MIME type and extension; reject unsupported types
- Query strings: validate and sanitize; max length enforced
- No SQL built from user input — SQLAlchemy ORM used exclusively
- File content is processed in isolated Celery tasks — pipeline failures do not affect API

## Prompt Injection Risk

Document content is included in LLM context. A malicious document could attempt to override system prompt instructions.

**Mitigations:**
- System prompt is prepended with clear grounding instruction and placed before any user content
- Context chunks are clearly delimited with source labels
- LLM response is presented as-is; no dynamic code execution based on LLM output

## Rate Limiting

- `/api/v1/conversations/{id}/query` — 10 requests/minute per user (LLM cost protection)
- `/api/v1/search` — 30 requests/minute per user
- `/auth/login` — 5 attempts/minute per IP (brute force protection)
- Implemented via `slowapi`

## File Upload Security

- Max file size enforced (configurable; default 50MB)
- MIME type validation on upload (not just extension)
- Files stored with UUID keys — no original filename in storage path
- No file execution — content extraction only via dedicated parsers

## Secrets Management

- All secrets via environment variables
- Never in source code, logs, or error messages
- `.env` never committed to version control

## Audit Logging

- Log user ID, action, resource ID, and timestamp for:
  - Login / logout / token refresh
  - Document upload / delete
  - Domain create / delete
  - LLM queries (query text, conversation ID, user ID)
- Structured JSON logs for easy parsing

## Data Exposure

- Deleted documents (`deleted_at IS NOT NULL`) excluded from all search results and API responses
- User passwords, token hashes never serialized in responses
- Internal error messages not leaked to clients — map to generic messages at HTTP layer

## Identified Risks

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Unauthorized knowledge access | Medium | High | Strict ownership checks per request |
| LLM API cost abuse | Medium | Medium | Rate limiting on query endpoints |
| Prompt injection via document | Low | Medium | System prompt structure + grounding enforcement |
| Pipeline resource exhaustion | Low | Medium | Task timeouts + max file size limits |
| Refresh token theft | Low | High | Token hashing + revocation + short access TTL |
| OpenAI API key exposure | Low | High | Env vars only; no logging of key value |
