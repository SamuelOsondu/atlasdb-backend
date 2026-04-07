"""
Service-layer integration tests for the retrieval component.

All tests use the real test database and mock only async_embed_text so that
no OpenAI calls are made. pgvector cosine similarity is exercised with real
math against the test DB.
"""
import uuid
from datetime import datetime, timezone

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import NotFoundError, ServiceUnavailableError
from app.documents.models import Document, DocumentChunk
from app.domains.models import KnowledgeDomain
from app.retrieval.service import search
from app.shared.enums import DocumentStatus
from app.users.models import User
from tests.retrieval.conftest import MATCH_EMBEDDING, QUERY_EMBEDDING


# ── helpers ────────────────────────────────────────────────────────────────────

def _mock_embed(monkeypatch, embedding=None):
    """Patch async_embed_text to return a deterministic vector without calling OpenAI."""
    vec = embedding if embedding is not None else QUERY_EMBEDDING

    async def _fake(text: str) -> list[float]:
        return vec

    monkeypatch.setattr("app.retrieval.service.async_embed_text", _fake)


# ── happy path ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_returns_matching_chunk(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    document_with_chunks,
    monkeypatch,
):
    """The matching chunk (similarity ≈ 1.0) is returned; orthogonal chunk is below threshold."""
    _mock_embed(monkeypatch)
    owner, _ = user_with_token
    _, chunk_match, chunk_ortho = document_with_chunks

    results = await search(
        query="find relevant content",
        user_id=owner.id,
        domain_id=None,
        top_k=10,
        db=db_session,
        threshold=0.5,  # match chunk passes (≈1.0), ortho chunk fails (≈0.0)
    )

    chunk_ids = [r.chunk_id for r in results]
    assert chunk_match.id in chunk_ids
    assert chunk_ortho.id not in chunk_ids


@pytest.mark.asyncio
async def test_search_result_has_correct_metadata(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    document_with_chunks,
    domain: KnowledgeDomain,
    monkeypatch,
):
    """Result fields are correctly mapped from DB rows."""
    _mock_embed(monkeypatch)
    owner, _ = user_with_token
    doc, chunk_match, _ = document_with_chunks

    results = await search(
        query="relevant",
        user_id=owner.id,
        domain_id=None,
        top_k=10,
        db=db_session,
        threshold=0.5,
    )

    assert len(results) >= 1
    r = results[0]
    assert r.document_id == doc.id
    assert r.domain_id == domain.id
    assert r.document_title == doc.title
    assert r.chunk_index == chunk_match.chunk_index
    assert "relevant" in r.text.lower() or r.text == chunk_match.text
    assert 0.9 <= r.score <= 1.0  # cos([1,0,...], [1,0,...]) = 1.0


@pytest.mark.asyncio
async def test_search_results_ordered_by_score_descending(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    document_with_chunks,
    monkeypatch,
):
    """Results must be ordered highest score first (guaranteed by pgvector ORDER BY)."""
    _mock_embed(monkeypatch)
    owner, _ = user_with_token

    results = await search(
        query="test",
        user_id=owner.id,
        domain_id=None,
        top_k=10,
        db=db_session,
        threshold=0.0,  # include everything so ordering can be verified
    )

    scores = [r.score for r in results]
    assert scores == sorted(scores, reverse=True)


@pytest.mark.asyncio
async def test_search_empty_when_no_indexed_docs(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    monkeypatch,
):
    """Empty result set is valid — not an error condition."""
    _mock_embed(monkeypatch)
    owner, _ = user_with_token

    results = await search(
        query="nothing here",
        user_id=owner.id,
        domain_id=None,
        top_k=10,
        db=db_session,
    )

    assert results == []


# ── ownership isolation ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_excludes_other_users_chunks(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    other_user_document_with_chunk,
    monkeypatch,
):
    """Chunks from another user's documents must never appear in results."""
    _mock_embed(monkeypatch)
    owner, _ = user_with_token
    _, other_chunk = other_user_document_with_chunk

    results = await search(
        query="test query",
        user_id=owner.id,
        domain_id=None,
        top_k=10,
        db=db_session,
        threshold=0.0,
    )

    returned_ids = [r.chunk_id for r in results]
    assert other_chunk.id not in returned_ids


# ── domain scoping ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_domain_scoped_returns_only_that_domain(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    second_domain: KnowledgeDomain,
    document_with_chunks,
    monkeypatch,
):
    """Scoping to domain A must not return chunks from domain B."""
    _mock_embed(monkeypatch)
    owner, _ = user_with_token
    doc, chunk_match, _ = document_with_chunks  # doc is in `domain`

    # Insert a chunk in the second domain
    doc_b = Document(
        owner_id=owner.id,
        domain_id=second_domain.id,
        title="Second Domain Doc",
        original_filename="b.txt",
        file_key=str(uuid.uuid4()),
        file_size=128,
        mime_type="text/plain",
        status=DocumentStatus.indexed.value,
        chunk_count=1,
    )
    db_session.add(doc_b)
    await db_session.flush()

    chunk_b = DocumentChunk(
        id=uuid.uuid4(),
        document_id=doc_b.id,
        chunk_index=0,
        text="Chunk in second domain.",
        embedding=MATCH_EMBEDDING,
    )
    db_session.add(chunk_b)
    await db_session.commit()

    # Search scoped to first domain
    results = await search(
        query="test",
        user_id=owner.id,
        domain_id=domain.id,
        top_k=10,
        db=db_session,
        threshold=0.5,
    )

    returned_ids = [r.chunk_id for r in results]
    assert chunk_match.id in returned_ids
    assert chunk_b.id not in returned_ids


@pytest.mark.asyncio
async def test_search_domain_not_owned_raises_not_found(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    other_domain: KnowledgeDomain,
    monkeypatch,
):
    """Searching with another user's domain_id raises NotFoundError (not 403)."""
    _mock_embed(monkeypatch)
    owner, _ = user_with_token

    with pytest.raises(NotFoundError):
        await search(
            query="test",
            user_id=owner.id,
            domain_id=other_domain.id,  # not owned by `owner`
            top_k=10,
            db=db_session,
        )


# ── soft-delete filter ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_excludes_soft_deleted_document_chunks(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    document_with_chunks,
    monkeypatch,
):
    """Chunks whose parent document has been soft-deleted must not appear."""
    _mock_embed(monkeypatch)
    owner, _ = user_with_token
    doc, chunk_match, _ = document_with_chunks

    # Soft-delete the document
    doc.deleted_at = datetime.now(timezone.utc)
    await db_session.commit()

    results = await search(
        query="test",
        user_id=owner.id,
        domain_id=None,
        top_k=10,
        db=db_session,
        threshold=0.0,
    )

    returned_ids = [r.chunk_id for r in results]
    assert chunk_match.id not in returned_ids


# ── threshold filtering ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_threshold_excludes_low_score_chunk(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    document_with_chunks,
    monkeypatch,
):
    """chunk_ortho (score ≈ 0.0) must be excluded when threshold > 0."""
    _mock_embed(monkeypatch)
    owner, _ = user_with_token
    _, chunk_match, chunk_ortho = document_with_chunks

    results = await search(
        query="test",
        user_id=owner.id,
        domain_id=None,
        top_k=10,
        db=db_session,
        threshold=0.5,
    )

    returned_ids = [r.chunk_id for r in results]
    assert chunk_ortho.id not in returned_ids
    # The matching chunk should still be present
    assert chunk_match.id in returned_ids


@pytest.mark.asyncio
async def test_search_zero_threshold_includes_all_chunks(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    document_with_chunks,
    monkeypatch,
):
    """With threshold=0.0 both high- and low-similarity chunks are returned."""
    _mock_embed(monkeypatch)
    owner, _ = user_with_token
    _, chunk_match, chunk_ortho = document_with_chunks

    results = await search(
        query="test",
        user_id=owner.id,
        domain_id=None,
        top_k=10,
        db=db_session,
        threshold=0.0,
    )

    returned_ids = [r.chunk_id for r in results]
    assert chunk_match.id in returned_ids
    assert chunk_ortho.id in returned_ids


# ── top_k ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_top_k_limits_result_count(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    document_with_chunks,
    monkeypatch,
):
    """top_k=1 must return at most 1 result."""
    _mock_embed(monkeypatch)
    owner, _ = user_with_token

    results = await search(
        query="test",
        user_id=owner.id,
        domain_id=None,
        top_k=1,
        db=db_session,
        threshold=0.0,
    )

    assert len(results) <= 1


# ── embedding failure ──────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_embedding_failure_raises_service_unavailable(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    monkeypatch,
):
    """An OpenAI exception during embedding must propagate as ServiceUnavailableError."""
    async def _fail(text: str):
        raise RuntimeError("OpenAI API is down")

    monkeypatch.setattr("app.retrieval.service.async_embed_text", _fail)
    owner, _ = user_with_token

    with pytest.raises(ServiceUnavailableError):
        await search(
            query="fail this",
            user_id=owner.id,
            domain_id=None,
            top_k=10,
            db=db_session,
        )


# ── chunks without embedding skipped ──────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_skips_chunks_without_embedding(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    indexed_document: Document,
    monkeypatch,
):
    """Chunks where embedding IS NULL must not appear in results (not yet indexed)."""
    _mock_embed(monkeypatch)
    owner, _ = user_with_token

    null_chunk = DocumentChunk(
        id=uuid.uuid4(),
        document_id=indexed_document.id,
        chunk_index=0,
        text="Chunk with no embedding yet.",
        embedding=None,  # explicitly unset
    )
    db_session.add(null_chunk)
    await db_session.commit()

    results = await search(
        query="test",
        user_id=owner.id,
        domain_id=None,
        top_k=10,
        db=db_session,
        threshold=0.0,
    )

    returned_ids = [r.chunk_id for r in results]
    assert null_chunk.id not in returned_ids
