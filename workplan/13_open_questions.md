# Open Questions — AtlasDB

## Q1 — Multi-Tenancy / User Isolation

**Question**: Are users isolated from each other? Can user A see or access user B's knowledge domains and documents?

**Options:**
- A) Full isolation — each user owns their own domains/documents, no sharing
- B) Shared knowledge base — all authenticated users can access all domains
- C) Organization-based — users belong to an org, share within org

**Default assumption**: Option A (full user isolation) — simpler data model, safer default.

**Impact if changed**: Data model gains an `organization` or `team` entity. Ownership checks shift from `user_id` to `org_id`. Affects domains, documents, conversations.

---

## Q2 — File Storage Backend

**Question**: Where should uploaded document files be stored in production?

**Options:**
- A) Local filesystem — dev only, not suitable for multi-instance or container restarts
- B) S3-compatible (AWS S3, MinIO, Cloudflare R2) — recommended for production
- C) MinIO (self-hosted S3-compatible) — good for on-premise deployments

**Default assumption**: Option B (S3-compatible), abstracted via config. Local filesystem for dev.

**Impact**: Low — storage abstraction already designed (`app/core/storage.py`). Just need to confirm provider for production env vars.

---

## Q3 — User Roles

**Question**: Should the system have an admin role with elevated capabilities?

**Options:**
- A) Single role — all authenticated users have the same access
- B) Two roles — admin + regular user

**Admin capabilities would include:**
- View all users
- Deactivate user accounts
- View all domains (cross-user)
- Force reprocess failed documents
- View system health/stats

**Default assumption**: Option B (admin + user). Worth designing now before the DB is seeded with production data.

**Impact**: `is_admin` boolean on `User` model (already included in schema plan). Admin endpoints in a separate router with `require_admin` dependency.

---

## Q4 — Queue: Celery vs RQ

**Question**: Do you have a preference or constraint between Celery and RQ?

**Recommendation**: Celery
- More mature retry and backoff support
- Flower monitoring dashboard
- Wider ecosystem and documentation
- Better suited for multi-stage chained tasks

**Default assumption**: Celery.

**Impact if RQ chosen**: Different task definition style, simpler setup, no Flower — acceptable tradeoff for simpler projects.

---

## Resolved Questions

_(none yet — all open)_
