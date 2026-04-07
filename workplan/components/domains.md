# Domains Component

## Purpose
Manages knowledge domains — logical collections of documents representing a specific knowledge area (e.g., "Engineering Docs", "Support Playbooks"). Domains are the primary organizational unit for documents and define the scope boundary for queries.

## Scope

### In Scope
- Create, read, update, delete knowledge domains
- Enforce ownership: users manage only their own domains
- Domain listing with pagination
- Domain used as scoping context for document uploads and search queries

### Out of Scope
- Document management within a domain (owned by `documents`)
- Cross-domain search logic (owned by `retrieval`)
- Sharing domains between users

## Responsibilities
- Own the `KnowledgeDomain` SQLAlchemy model
- CRUD endpoints for knowledge domains
- Enforce that users can only create/read/update/delete their own domains
- Provide `get_domain_or_403` helper used by documents and retrieval to validate ownership before operations

## Dependencies
- `auth` (get_current_user)
- `core/database.py`

## Related Models
- `KnowledgeDomain`

## Related Endpoints
- `POST /api/v1/domains` — create domain
- `GET /api/v1/domains` — list own domains (paginated)
- `GET /api/v1/domains/{domain_id}` — get domain detail
- `PATCH /api/v1/domains/{domain_id}` — update domain name/description
- `DELETE /api/v1/domains/{domain_id}` — delete domain (and cascade soft-delete documents)

## Business Rules
- A domain belongs to exactly one user (owner)
- User can only see and manage their own domains
- Domain name must be unique per user (not globally)
- Deleting a domain soft-deletes all documents in that domain
- A domain can have zero documents (valid empty collection)
- Domain ID is used as optional scope parameter in search and conversation creation

## Security Considerations
- Ownership check required on every domain operation — verify `domain.owner_id == current_user.id`
- Domain ID in path must be validated against DB — return 404 (not 403) when domain doesn't exist to avoid enumeration
- Delete operation cascades — confirm intent with clear response message

## Performance Considerations
- Domain listing: paginated, indexed on `owner_id`
- Domain detail: single DB fetch by ID + owner_id filter (one query)
- Domain count included in list response (SQL COUNT, not ORM load-all)

## Reliability Considerations
- Domain deletion cascades soft-delete to documents — this must be in a DB transaction
- If cascade soft-delete partially fails, no domain should be deleted (rollback)

## Testing Expectations
- Integration: CRUD flows for domains
- Permission: user cannot access another user's domain (returns 404)
- Business rule: domain name uniqueness per user
- Cascade: deleting domain soft-deletes its documents

## Implementation Notes
- `domains/models.py`: `KnowledgeDomain` model
- `domains/service.py`: CRUD with ownership enforcement. `get_domain_or_403(domain_id, user_id)` helper used by other components.
- `domains/schemas.py`: `DomainCreateRequest`, `DomainUpdateRequest`, `DomainResponse`, `DomainListResponse`
- Cascade soft-delete on domain delete: `UPDATE documents SET deleted_at = NOW() WHERE domain_id = :domain_id AND deleted_at IS NULL`

## Status
complete

## Pending Tasks
- None

## Completion Notes
- `app/domains/models.py`: `KnowledgeDomain` with `UniqueConstraint("owner_id", "name")` — name unique per owner, not globally
- `app/domains/service.py`: full CRUD + `get_domain_or_404` (returns 404 for both non-existent and foreign domains — prevents enumeration); cascade soft-delete on delete uses deferred `Document` import (resolves once documents component is implemented); `IntegrityError` caught for duplicate name on create and update
- `app/domains/router.py`: all 5 endpoints; `PATCH` uses `model_fields_set` to distinguish omitted vs. null `description`; paginated list uses `PaginatedResponse`
- `alembic/versions/003_create_knowledge_domains.py`: creates table with unique constraint and owner_id index
- `alembic/env.py` + `tests/conftest.py`: updated with `KnowledgeDomain` import
- Tests: 15 service tests + 19 router tests covering full CRUD, ownership isolation (404 not 403), name uniqueness per-user, cross-user same-name allowed, pagination, cascade delete verification
