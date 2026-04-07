"""
Fixtures for retrieval (semantic search) tests.

Uses distinct email addresses from other test modules to prevent unique-constraint
violations when the full test suite runs in a single pytest session.

Embedding constants
-------------------
QUERY_EMBEDDING   — the vector returned by the mocked async_embed_text.
MATCH_EMBEDDING   — identical to QUERY_EMBEDDING → cosine similarity ≈ 1.0.
ORTHO_EMBEDDING   — orthogonal to QUERY_EMBEDDING → cosine similarity ≈ 0.0.

Tests that exercise similarity filtering should monkeypatch
`app.retrieval.service.async_embed_text` to return `QUERY_EMBEDDING`.
"""
import uuid

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import RegisterRequest
from app.auth.service import register_user
from app.documents.models import Document, DocumentChunk
from app.domains.models import KnowledgeDomain
from app.domains.schemas import DomainCreateRequest
from app.domains.service import create_domain
from app.shared.enums import DocumentStatus
from app.users.models import User

# ---------------------------------------------------------------------------
# Deterministic embedding vectors (1536-dimensional unit vectors)
# ---------------------------------------------------------------------------

# The "query" embedding that tests will inject via monkeypatch.
QUERY_EMBEDDING: list[float] = [1.0] + [0.0] * 1535

# A chunk embedding that is identical to the query → similarity ≈ 1.0.
MATCH_EMBEDDING: list[float] = [1.0] + [0.0] * 1535

# A chunk embedding orthogonal to the query → similarity ≈ 0.0.
ORTHO_EMBEDDING: list[float] = [0.0, 1.0] + [0.0] * 1534


# ---------------------------------------------------------------------------
# User fixtures — unique emails to avoid cross-module conflicts
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def user_with_token(db_session: AsyncSession) -> tuple[User, str]:
    user, tokens = await register_user(
        RegisterRequest(email="search_owner@example.com", password="password1"),
        db_session,
    )
    return user, tokens.access_token


@pytest_asyncio.fixture
async def other_user_with_token(db_session: AsyncSession) -> tuple[User, str]:
    user, tokens = await register_user(
        RegisterRequest(email="search_other@example.com", password="password1"),
        db_session,
    )
    return user, tokens.access_token


# ---------------------------------------------------------------------------
# Domain fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def domain(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
) -> KnowledgeDomain:
    owner, _ = user_with_token
    return await create_domain(
        DomainCreateRequest(name="Search Test Domain"),
        owner.id,
        db_session,
    )


@pytest_asyncio.fixture
async def other_domain(
    db_session: AsyncSession,
    other_user_with_token: tuple[User, str],
) -> KnowledgeDomain:
    owner, _ = other_user_with_token
    return await create_domain(
        DomainCreateRequest(name="Other User Domain"),
        owner.id,
        db_session,
    )


@pytest_asyncio.fixture
async def second_domain(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
) -> KnowledgeDomain:
    """A second domain owned by the primary user — used for domain-scoping tests."""
    owner, _ = user_with_token
    return await create_domain(
        DomainCreateRequest(name="Second Search Domain"),
        owner.id,
        db_session,
    )


# ---------------------------------------------------------------------------
# Document + chunk fixtures
# ---------------------------------------------------------------------------

@pytest_asyncio.fixture
async def indexed_document(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
) -> Document:
    """An indexed document in the primary user's domain."""
    owner, _ = user_with_token
    doc = Document(
        owner_id=owner.id,
        domain_id=domain.id,
        title="Retrieval Test Document",
        original_filename="retrieval.txt",
        file_key=str(uuid.uuid4()),
        file_size=512,
        mime_type="text/plain",
        status=DocumentStatus.indexed.value,
        chunk_count=2,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest_asyncio.fixture
async def document_with_chunks(
    db_session: AsyncSession,
    indexed_document: Document,
) -> tuple[Document, DocumentChunk, DocumentChunk]:
    """
    Attaches two chunks to `indexed_document`:
      chunk_match  — MATCH_EMBEDDING (similarity ≈ 1.0 with QUERY_EMBEDDING)
      chunk_ortho  — ORTHO_EMBEDDING (similarity ≈ 0.0 with QUERY_EMBEDDING)
    """
    chunk_match = DocumentChunk(
        id=uuid.uuid4(),
        document_id=indexed_document.id,
        chunk_index=0,
        text="This is the relevant chunk that matches the query.",
        embedding=MATCH_EMBEDDING,
    )
    chunk_ortho = DocumentChunk(
        id=uuid.uuid4(),
        document_id=indexed_document.id,
        chunk_index=1,
        text="This chunk is completely unrelated and orthogonal.",
        embedding=ORTHO_EMBEDDING,
    )
    db_session.add_all([chunk_match, chunk_ortho])
    await db_session.commit()
    return indexed_document, chunk_match, chunk_ortho


@pytest_asyncio.fixture
async def other_user_document_with_chunk(
    db_session: AsyncSession,
    other_user_with_token: tuple[User, str],
    other_domain: KnowledgeDomain,
) -> tuple[Document, DocumentChunk]:
    """A document + chunk owned by other_user — used for ownership isolation tests."""
    owner, _ = other_user_with_token
    doc = Document(
        owner_id=owner.id,
        domain_id=other_domain.id,
        title="Other User Document",
        original_filename="other.txt",
        file_key=str(uuid.uuid4()),
        file_size=256,
        mime_type="text/plain",
        status=DocumentStatus.indexed.value,
        chunk_count=1,
    )
    db_session.add(doc)
    await db_session.flush()

    chunk = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc.id,
        chunk_index=0,
        text="Other user's sensitive content.",
        embedding=MATCH_EMBEDDING,  # Same embedding — would match query if not filtered
    )
    db_session.add(chunk)
    await db_session.commit()
    return doc, chunk
