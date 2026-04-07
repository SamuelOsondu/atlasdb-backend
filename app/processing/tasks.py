"""
Celery processing pipeline tasks.

Entry point: extract_text(document_id)
Pipeline: extract → chunk → embed → index
All stages run within the same task to avoid passing large data through Redis.
"""
import asyncio
import logging
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from celery import Task
from sqlalchemy import delete as sa_delete

from app.celery_app import celery_app
from app.core.config import settings
from app.core.openai_client import embed_texts
from app.core.storage import get_storage
from app.documents.models import Document, DocumentChunk
from app.processing.chunker import chunk_text
from app.processing.extractors import extract_text_from_content
from app.shared.enums import DocumentStatus

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Overridable session factory — replaced in tests to point at the test DB.
# ---------------------------------------------------------------------------

def _new_session():
    """Create a new sync DB session. Replaced in tests via monkeypatching."""
    from app.core.database import SyncSessionLocal  # noqa: PLC0415
    return SyncSessionLocal()


@contextmanager
def _db():
    """Context manager that opens a sync session and guarantees close + rollback on error."""
    session = _new_session()
    try:
        yield session
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mark_failed(document_id: uuid.UUID, error: str) -> None:
    """Update document status to 'failed' and record the error message."""
    try:
        with _db() as db:
            doc = db.get(Document, document_id)
            if doc is not None:
                doc.status = DocumentStatus.failed.value
                doc.error_message = error[:2000]
                doc.updated_at = datetime.now(timezone.utc)
                db.commit()
    except Exception:
        logger.exception("Failed to write 'failed' status for document %s", document_id)


# ---------------------------------------------------------------------------
# Pipeline stages (plain functions — not Celery tasks)
# ---------------------------------------------------------------------------

def _stage_extract(file_key: str, mime_type: str) -> str:
    storage = get_storage()
    file_content = asyncio.run(storage.retrieve(file_key))
    return extract_text_from_content(file_content, mime_type)


def _stage_chunk(raw_text: str) -> list[str]:
    return chunk_text(
        raw_text,
        max_tokens=settings.CHUNK_MAX_TOKENS,
        overlap=settings.CHUNK_OVERLAP_TOKENS,
    )


def _stage_embed(chunk_texts_list: list[str]) -> list[list[float]]:
    return embed_texts(chunk_texts_list)


def _stage_index(doc_uuid: uuid.UUID, chunk_texts_list: list[str], embeddings: list[list[float]]) -> int:
    with _db() as db:
        db.execute(sa_delete(DocumentChunk).where(DocumentChunk.document_id == doc_uuid))
        objects = [
            DocumentChunk(
                document_id=doc_uuid,
                chunk_index=i,
                text=chunk_texts_list[i],
                embedding=embeddings[i],
            )
            for i in range(len(chunk_texts_list))
        ]
        db.bulk_save_objects(objects)
        doc = db.get(Document, doc_uuid)
        if doc is not None:
            doc.status = DocumentStatus.indexed.value
            doc.chunk_count = len(objects)
            doc.error_message = None
            doc.updated_at = datetime.now(timezone.utc)
        db.commit()
    return len(objects)


# ---------------------------------------------------------------------------
# Celery task
# ---------------------------------------------------------------------------

@celery_app.task(
    name="app.processing.tasks.extract_text",
    bind=True,
    queue="cpu_bound",
    max_retries=3,
    time_limit=600,
    soft_time_limit=540,
    acks_late=True,
)
def extract_text(self: Task, document_id: str) -> None:
    """
    Full pipeline orchestrator for a single document.
    Stages: extract → chunk → embed → index.
    Called by documents.service.enqueue_processing after upload commit.
    """
    doc_uuid = uuid.UUID(document_id)

    # ── Guard: load document and mark as processing ────────────────────────
    with _db() as db:
        doc = db.get(Document, doc_uuid)
        if doc is None:
            logger.error("Pipeline: document %s not found — aborting", document_id)
            return
        if doc.deleted_at is not None:
            logger.info("Pipeline: document %s is soft-deleted — skipping", document_id)
            return
        if doc.status == DocumentStatus.processing.value:
            logger.info("Pipeline: document %s already processing — skipping duplicate run", document_id)
            return

        doc.status = DocumentStatus.processing.value
        doc.error_message = None
        doc.updated_at = datetime.now(timezone.utc)
        db.commit()
        file_key = doc.file_key
        mime_type = doc.mime_type

    try:
        raw_text = _stage_extract(file_key, mime_type)

        if not raw_text.strip():
            _mark_failed(doc_uuid, "No text could be extracted from the document")
            return

        chunk_texts_list = _stage_chunk(raw_text)

        if not chunk_texts_list:
            _mark_failed(doc_uuid, "Document produced no chunks after text extraction")
            return

        embeddings = _stage_embed(chunk_texts_list)

        if len(embeddings) != len(chunk_texts_list):
            _mark_failed(doc_uuid, "Embedding count mismatch — pipeline aborted")
            return

        n = _stage_index(doc_uuid, chunk_texts_list, embeddings)
        logger.info("Pipeline: document %s indexed — %d chunks", document_id, n)

    except Exception as exc:
        logger.error("Pipeline: document %s failed: %s", document_id, exc, exc_info=True)
        _mark_failed(doc_uuid, str(exc))
        if self.request.retries < self.max_retries:
            raise self.retry(
                exc=exc,
                countdown=min(60 * (2 ** self.request.retries), 600),
            )
        logger.error("Pipeline: document %s exhausted all retries", document_id)
