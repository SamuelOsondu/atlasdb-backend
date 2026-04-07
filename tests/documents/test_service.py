"""
Service-layer tests for the documents component.

All file I/O uses InMemoryStorage. Celery task enqueue is silently skipped
because the processing component is not yet implemented.
"""
import io
import uuid

import pytest
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from starlette.datastructures import Headers

from app.core.exceptions import AppValidationError, ConflictError, FileTooLargeError, NotFoundError
from app.documents.models import Document, DocumentChunk
from app.documents.service import (
    get_any_document_or_404,
    get_document_or_404,
    list_documents,
    reprocess_document,
    soft_delete_document,
    upload_document,
)
from app.domains.models import KnowledgeDomain
from app.shared.enums import DocumentStatus
from app.users.models import User
from tests.documents.conftest import InMemoryStorage


def _make_upload(content: bytes = b"hello world", filename: str = "doc.txt",
                 content_type: str = "text/plain") -> UploadFile:
    return UploadFile(
        filename=filename,
        file=io.BytesIO(content),
        headers=Headers({"content-type": content_type}),
    )


# ── upload_document ────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_returns_pending_document(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    mock_storage: InMemoryStorage,
):
    owner, _ = user_with_token
    upload = _make_upload(b"pdf bytes", "report.pdf", "application/pdf")
    doc = await upload_document(
        domain_id=domain.id,
        file=upload,
        title="Annual Report",
        owner_id=owner.id,
        storage=mock_storage,
        db=db_session,
    )
    assert doc.id is not None
    assert doc.status == DocumentStatus.pending.value
    assert doc.title == "Annual Report"
    assert doc.original_filename == "report.pdf"
    assert doc.mime_type == "application/pdf"
    assert doc.owner_id == owner.id
    assert doc.domain_id == domain.id
    assert doc.file_size == len(b"pdf bytes")


@pytest.mark.asyncio
async def test_upload_uses_filename_when_no_title(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    mock_storage: InMemoryStorage,
):
    owner, _ = user_with_token
    upload = _make_upload(b"data", "notes.txt", "text/plain")
    doc = await upload_document(
        domain_id=domain.id,
        file=upload,
        title=None,
        owner_id=owner.id,
        storage=mock_storage,
        db=db_session,
    )
    assert doc.title == "notes.txt"


@pytest.mark.asyncio
async def test_upload_stores_file_in_storage(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    mock_storage: InMemoryStorage,
):
    owner, _ = user_with_token
    content = b"markdown content"
    upload = _make_upload(content, "readme.md", "text/markdown")
    doc = await upload_document(
        domain_id=domain.id,
        file=upload,
        title=None,
        owner_id=owner.id,
        storage=mock_storage,
        db=db_session,
    )
    stored = await mock_storage.retrieve(doc.file_key)
    assert stored == content


@pytest.mark.asyncio
async def test_upload_rejects_foreign_domain(
    db_session: AsyncSession,
    other_user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    mock_storage: InMemoryStorage,
):
    other, _ = other_user_with_token
    upload = _make_upload()
    with pytest.raises(NotFoundError):
        await upload_document(
            domain_id=domain.id,
            file=upload,
            title=None,
            owner_id=other.id,
            storage=mock_storage,
            db=db_session,
        )


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_mime(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    mock_storage: InMemoryStorage,
):
    owner, _ = user_with_token
    upload = _make_upload(b"<html>", "page.html", "text/html")
    with pytest.raises(AppValidationError):
        await upload_document(
            domain_id=domain.id,
            file=upload,
            title=None,
            owner_id=owner.id,
            storage=mock_storage,
            db=db_session,
        )


@pytest.mark.asyncio
async def test_upload_rejects_file_too_large(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    mock_storage: InMemoryStorage,
    monkeypatch,
):
    owner, _ = user_with_token
    # Patch MAX_FILE_SIZE_MB to 1 so we can use a small file in the test.
    from app.core import config as config_mod
    monkeypatch.setattr(config_mod.settings, "MAX_FILE_SIZE_MB", 1)

    oversized = b"x" * (1 * 1024 * 1024 + 1)
    upload = _make_upload(oversized, "big.txt", "text/plain")
    with pytest.raises(FileTooLargeError):
        await upload_document(
            domain_id=domain.id,
            file=upload,
            title=None,
            owner_id=owner.id,
            storage=mock_storage,
            db=db_session,
        )


@pytest.mark.asyncio
async def test_upload_allows_duplicate_filenames(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    mock_storage: InMemoryStorage,
):
    """Same filename in same domain is allowed — each upload gets its own record."""
    owner, _ = user_with_token
    doc1 = await upload_document(
        domain_id=domain.id,
        file=_make_upload(b"v1", "report.txt", "text/plain"),
        title="v1",
        owner_id=owner.id,
        storage=mock_storage,
        db=db_session,
    )
    doc2 = await upload_document(
        domain_id=domain.id,
        file=_make_upload(b"v2", "report.txt", "text/plain"),
        title="v2",
        owner_id=owner.id,
        storage=mock_storage,
        db=db_session,
    )
    assert doc1.id != doc2.id


# ── get_document_or_404 ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_document_returns_own(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    document: Document,
):
    owner, _ = user_with_token
    fetched = await get_document_or_404(document.id, owner.id, db_session)
    assert fetched.id == document.id


@pytest.mark.asyncio
async def test_get_document_raises_for_foreign(
    db_session: AsyncSession,
    other_user_with_token: tuple[User, str],
    document: Document,
):
    other, _ = other_user_with_token
    with pytest.raises(NotFoundError):
        await get_document_or_404(document.id, other.id, db_session)


@pytest.mark.asyncio
async def test_get_document_raises_for_nonexistent(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
):
    owner, _ = user_with_token
    with pytest.raises(NotFoundError):
        await get_document_or_404(uuid.uuid4(), owner.id, db_session)


# ── list_documents ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_documents_returns_domain_docs(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    document: Document,
):
    owner, _ = user_with_token
    docs, total = await list_documents(domain.id, owner.id, page=1, page_size=20, db=db_session)
    ids = [d.id for d in docs]
    assert document.id in ids
    assert total >= 1


@pytest.mark.asyncio
async def test_list_documents_excludes_deleted(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    document: Document,
):
    owner, _ = user_with_token
    await soft_delete_document(document, db_session)
    docs, total = await list_documents(domain.id, owner.id, page=1, page_size=20, db=db_session)
    ids = [d.id for d in docs]
    assert document.id not in ids


@pytest.mark.asyncio
async def test_list_documents_pagination(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    mock_storage: InMemoryStorage,
):
    owner, _ = user_with_token
    for i in range(5):
        await upload_document(
            domain_id=domain.id,
            file=_make_upload(f"content {i}".encode(), f"doc{i}.txt", "text/plain"),
            title=f"Doc {i}",
            owner_id=owner.id,
            storage=mock_storage,
            db=db_session,
        )
    docs, total = await list_documents(domain.id, owner.id, page=1, page_size=2, db=db_session)
    assert len(docs) == 2
    assert total >= 5


@pytest.mark.asyncio
async def test_list_documents_rejects_foreign_domain(
    db_session: AsyncSession,
    other_user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
):
    other, _ = other_user_with_token
    with pytest.raises(NotFoundError):
        await list_documents(domain.id, other.id, page=1, page_size=20, db=db_session)


# ── soft_delete_document ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_soft_delete_sets_deleted_at(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    document: Document,
):
    owner, _ = user_with_token
    await soft_delete_document(document, db_session)
    with pytest.raises(NotFoundError):
        await get_document_or_404(document.id, owner.id, db_session)


@pytest.mark.asyncio
async def test_soft_delete_processing_document_raises_409(
    db_session: AsyncSession,
    processing_document: Document,
):
    with pytest.raises(ConflictError):
        await soft_delete_document(processing_document, db_session)


# ── reprocess_document ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_reprocess_resets_to_pending(
    db_session: AsyncSession,
    indexed_document: Document,
):
    reprocessed = await reprocess_document(indexed_document, db_session)
    assert reprocessed.status == DocumentStatus.pending.value


@pytest.mark.asyncio
async def test_reprocess_clears_chunks(
    db_session: AsyncSession,
    indexed_document: Document,
):
    # Insert some fake chunks.
    for i in range(3):
        db_session.add(DocumentChunk(
            document_id=indexed_document.id,
            chunk_index=i,
            text=f"chunk {i}",
        ))
    await db_session.commit()

    await reprocess_document(indexed_document, db_session)

    from sqlalchemy import select
    result = await db_session.execute(
        select(DocumentChunk).where(DocumentChunk.document_id == indexed_document.id)
    )
    assert result.scalars().all() == []


# ── get_any_document_or_404 ────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_any_document_finds_any_owner(
    db_session: AsyncSession,
    document: Document,
):
    fetched = await get_any_document_or_404(document.id, db_session)
    assert fetched.id == document.id


@pytest.mark.asyncio
async def test_get_any_document_raises_for_deleted(
    db_session: AsyncSession,
    document: Document,
):
    await soft_delete_document(document, db_session)
    with pytest.raises(NotFoundError):
        await get_any_document_or_404(document.id, db_session)
