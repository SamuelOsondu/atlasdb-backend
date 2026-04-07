"""
Documents service — upload lifecycle, ownership enforcement, status tracking,
soft delete, and admin reprocessing.

Celery task enqueue is always performed AFTER the DB commit to avoid phantom
jobs on rollback. If the enqueue step fails the document stays in `pending`
status and can be recovered via the admin reprocess endpoint.
"""
import logging
import uuid
from datetime import datetime, timezone

from fastapi import UploadFile
from sqlalchemy import delete as sa_delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.core.exceptions import ConflictError, NotFoundError
from app.core.storage import StorageBackend
from app.documents.models import Document, DocumentChunk
from app.documents.validation import validate_and_read_upload
from app.domains.service import get_domain_or_404
from app.shared.enums import DocumentStatus


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def enqueue_processing(document_id: uuid.UUID) -> None:
    """
    Enqueue the Celery extract_text task for a document.

    Uses a deferred import so the service works correctly before the
    processing_pipeline component is implemented. Once the module exists
    the import resolves and tasks are dispatched on every upload.

    If the processing module is unavailable (expected during development) the call
    is a no-op. Any other exception (e.g., Celery broker unreachable) is logged as
    a warning — the document stays in `pending` and can be recovered via admin reprocess.
    """
    try:
        from app.processing.tasks import extract_text  # noqa: PLC0415
        extract_text.delay(str(document_id))
    except ImportError:
        pass  # processing_pipeline component not yet implemented — expected
    except Exception:
        logger.warning(
            "Failed to enqueue processing task for document %s — "
            "document will remain in 'pending' status until reprocessed.",
            document_id,
            exc_info=True,
        )


async def count_document_chunks(document_id: uuid.UUID, db: AsyncSession) -> int:
    """Return the number of DocumentChunk rows for a given document."""
    result = await db.execute(
        select(func.count())
        .select_from(DocumentChunk)
        .where(DocumentChunk.document_id == document_id)
    )
    return result.scalar_one()


# ---------------------------------------------------------------------------
# Public service functions
# ---------------------------------------------------------------------------

async def upload_document(
    domain_id: uuid.UUID,
    file: UploadFile,
    title: str | None,
    owner_id: uuid.UUID,
    storage: StorageBackend,
    db: AsyncSession,
) -> Document:
    """
    Full upload flow:
      1. Verify domain ownership.
      2. Validate file type and size (streaming read).
      3. Store file via storage abstraction.
      4. Create Document record (status=pending).
      5. Commit.
      6. Enqueue processing job (post-commit).
    """
    # Step 1 — domain ownership guard (raises NotFoundError on failure)
    await get_domain_or_404(domain_id, owner_id, db)

    # Step 2 — validate type + stream into memory (capped at MAX_FILE_SIZE_MB)
    file_bytes, mime_type = await validate_and_read_upload(file, settings.MAX_FILE_SIZE_MB)

    # Step 3 — store file under a UUID-derived key (original filename is metadata only)
    sanitized_name = f"{uuid.uuid4()}"
    file_key = await storage.store(file_bytes, sanitized_name, mime_type)

    # Step 4 — persist DB record
    doc = Document(
        owner_id=owner_id,
        domain_id=domain_id,
        title=(title or file.filename or "Untitled").strip() or "Untitled",
        original_filename=file.filename or "",
        file_key=file_key,
        file_size=len(file_bytes),
        mime_type=mime_type,
        status=DocumentStatus.pending.value,
    )
    db.add(doc)

    # Step 5 — commit BEFORE enqueuing to avoid phantom jobs on rollback
    await db.commit()
    await db.refresh(doc)

    # Step 6 — enqueue after successful commit
    enqueue_processing(doc.id)

    return doc


async def get_document_or_404(
    document_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: AsyncSession,
) -> Document:
    """
    Fetch an active (non-deleted) document that belongs to owner_id.
    Returns 404 for both non-existent and foreign documents — prevents enumeration.
    """
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.owner_id == owner_id,
            Document.deleted_at.is_(None),
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise NotFoundError("Document not found")
    return doc


async def get_any_document_or_404(
    document_id: uuid.UUID,
    db: AsyncSession,
) -> Document:
    """
    Admin variant — no ownership filter, but still excludes soft-deleted records.
    Used by the admin reprocess endpoint.
    """
    result = await db.execute(
        select(Document).where(
            Document.id == document_id,
            Document.deleted_at.is_(None),
        )
    )
    doc = result.scalar_one_or_none()
    if doc is None:
        raise NotFoundError("Document not found")
    return doc


async def list_documents(
    domain_id: uuid.UUID,
    owner_id: uuid.UUID,
    page: int,
    page_size: int,
    db: AsyncSession,
) -> tuple[list[Document], int]:
    """
    List active documents in a domain owned by owner_id.
    Verifies domain ownership before listing (raises NotFoundError on failure).
    """
    # Domain ownership guard — prevents listing another user's domain documents.
    await get_domain_or_404(domain_id, owner_id, db)

    base_filter = (
        Document.domain_id == domain_id,
        Document.deleted_at.is_(None),
    )

    total: int = (
        await db.execute(
            select(func.count()).select_from(Document).where(*base_filter)
        )
    ).scalar_one()

    offset = (page - 1) * page_size
    docs = list(
        (
            await db.execute(
                select(Document)
                .where(*base_filter)
                .order_by(Document.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
        ).scalars()
    )
    return docs, total


async def soft_delete_document(document: Document, db: AsyncSession) -> None:
    """
    Soft-delete a document by setting deleted_at.
    Raises ConflictError if the document is currently being processed.
    """
    if document.status == DocumentStatus.processing.value:
        raise ConflictError(
            "Document is currently being processed and cannot be deleted. "
            "Wait for processing to complete or fail before deleting."
        )

    document.deleted_at = datetime.now(timezone.utc)
    document.updated_at = datetime.now(timezone.utc)
    await db.commit()


async def reprocess_document(document: Document, db: AsyncSession) -> Document:
    """
    Admin-only reprocess flow:
      1. Clear all existing chunks.
      2. Reset document status to pending.
      3. Commit.
      4. Re-enqueue the processing job.
    """
    # Clear existing chunks so processing starts fresh.
    await db.execute(
        sa_delete(DocumentChunk).where(DocumentChunk.document_id == document.id)
    )

    document.status = DocumentStatus.pending.value
    document.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(document)

    # Re-enqueue post-commit.
    enqueue_processing(document.id)

    return document
