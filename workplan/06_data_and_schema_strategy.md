# Data and Schema Strategy — AtlasDB

## Key Entities

### users
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| email | VARCHAR UNIQUE NOT NULL | |
| hashed_password | VARCHAR NOT NULL | bcrypt |
| full_name | VARCHAR | |
| is_active | BOOLEAN DEFAULT true | |
| is_admin | BOOLEAN DEFAULT false | |
| created_at | TIMESTAMP WITH TIME ZONE | |
| updated_at | TIMESTAMP WITH TIME ZONE | |

### refresh_tokens
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID FK → users | |
| token_hash | VARCHAR NOT NULL | hashed for storage |
| expires_at | TIMESTAMP WITH TIME ZONE | |
| revoked | BOOLEAN DEFAULT false | |
| created_at | TIMESTAMP WITH TIME ZONE | |

### knowledge_domains
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| owner_id | UUID FK → users | pending: shared vs isolated |
| name | VARCHAR NOT NULL | |
| description | TEXT | |
| created_at | TIMESTAMP WITH TIME ZONE | |
| updated_at | TIMESTAMP WITH TIME ZONE | |

Index: `(owner_id)`

### documents
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| domain_id | UUID FK → knowledge_domains | |
| owner_id | UUID FK → users | denormalized for query convenience |
| title | VARCHAR NOT NULL | |
| file_key | VARCHAR NOT NULL | storage key/path |
| file_name | VARCHAR NOT NULL | original filename |
| file_type | VARCHAR NOT NULL | pdf, md, txt |
| file_size_bytes | BIGINT | |
| status | VARCHAR NOT NULL | pending, processing, indexed, failed |
| error_message | TEXT | populated on failure |
| chunk_count | INTEGER | populated after chunking |
| created_at | TIMESTAMP WITH TIME ZONE | |
| updated_at | TIMESTAMP WITH TIME ZONE | |
| deleted_at | TIMESTAMP WITH TIME ZONE | soft delete |

Indexes: `(domain_id)`, `(owner_id)`, `(status)`, `(deleted_at)` where null

### document_chunks
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| document_id | UUID FK → documents ON DELETE CASCADE | |
| chunk_index | INTEGER NOT NULL | position within document |
| content | TEXT NOT NULL | raw text of chunk |
| token_count | INTEGER | pre-computed |
| embedding | vector(1536) | pgvector column |
| metadata | JSONB | section heading, page number, etc. |
| created_at | TIMESTAMP WITH TIME ZONE | |

Indexes:
- `(document_id, chunk_index)` — for ordered chunk retrieval
- IVFFlat index on `embedding` using cosine distance: `CREATE INDEX ON document_chunks USING ivfflat (embedding vector_cosine_ops) WITH (lists = 100);`

**No soft delete on chunks.** Chunks are hard-deleted when document is deleted. Recreatable from source document.

### conversations
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| user_id | UUID FK → users | |
| title | VARCHAR | auto-generated or user-set |
| domain_id | UUID FK → knowledge_domains | nullable = cross-domain |
| created_at | TIMESTAMP WITH TIME ZONE | |
| updated_at | TIMESTAMP WITH TIME ZONE | |

Index: `(user_id)`

### messages
| Column | Type | Notes |
|---|---|---|
| id | UUID (PK) | |
| conversation_id | UUID FK → conversations | |
| role | VARCHAR NOT NULL | user, assistant |
| content | TEXT NOT NULL | |
| citations | JSONB | array of citation objects |
| created_at | TIMESTAMP WITH TIME ZONE | |

Index: `(conversation_id, created_at)` — cursor-based pagination

## Relationships

- User → many KnowledgeDomains (1:N)
- KnowledgeDomain → many Documents (1:N)
- Document → many DocumentChunks (1:N, cascade delete)
- User → many Conversations (1:N)
- Conversation → many Messages (1:N)

## Transaction Handling

- Document creation (DB record + enqueue job): single transaction for DB write; queue enqueue after commit
- Chunk creation during pipeline: batch insert within a transaction per document
- Message persistence after streaming: write message + assistant response in single transaction after stream completes

## Soft Delete Strategy

- Documents: soft delete via `deleted_at`. All queries filter `WHERE deleted_at IS NULL` by default.
- Soft-deleted documents excluded from search and chunk retrieval.
- Restore: set `deleted_at = NULL` (admin only).
- Cascading: soft-deleting a document does NOT cascade to chunks automatically — chunks remain indexed but are excluded via join on parent document's `deleted_at`.

## Pagination

- **Offset-based**: Documents, knowledge domains, conversations (simple lists, stable order)
- **Cursor-based**: Messages within a conversation (ordered by `created_at`, cursor = last message ID)
- Default page size: 20. Max: 100.
- All list responses include `total`, `page`, `page_size` or `next_cursor`.

## Indexing Strategy

All FK columns indexed. Frequently filtered columns indexed (status, deleted_at, domain_id). Composite index on messages for cursor pagination. IVFFlat on embedding column.

## Migration Notes

- Migration `001`: enable pgvector extension
- Migration `002`: create users, refresh_tokens
- Migration `003`: knowledge_domains, documents, document_chunks (with vector column)
- Migration `004`: conversations, messages
- IVFFlat index created after data load (not at schema creation) for performance — see runbook notes
