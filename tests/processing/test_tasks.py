"""
Integration tests for the processing pipeline task.

Uses a real test database (via sync session) and mocks:
  - embed_texts  — returns deterministic fake embeddings (avoids real OpenAI calls)
  - get_storage  — returns InMemoryStorage with pre-loaded file content

All tests that use the `pipeline_document` async fixture are `async def` because
pytest-asyncio requires async test functions when async fixtures are involved.
`throw=False` is passed to every `task.apply()` call so that Celery's internal
Retry/MaxRetriesExceeded exceptions don't propagate to the test process.
"""
import io
import os
import uuid

import pytest
import pytest_asyncio
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from app.documents.models import Document, DocumentChunk
from app.shared.enums import DocumentStatus
from app.users.models import User
from tests.documents.conftest import InMemoryStorage

# Sync test DB URL — derived from the same env var the async test infra uses.
_SYNC_TEST_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/atlasdb_test",
).replace("+asyncpg", "+psycopg2").replace("postgresql://", "postgresql+psycopg2://")


# ── sync session infrastructure ────────────────────────────────────────────────

@pytest.fixture(scope="session")
def sync_engine(db_engine):
    """Session-scoped sync engine. Depends on db_engine so the schema is created first."""
    engine = create_engine(_SYNC_TEST_URL)
    yield engine
    engine.dispose()


@pytest.fixture
def sync_session_factory(sync_engine):
    """Function-scoped factory; each call creates a fresh Session."""
    return sessionmaker(bind=sync_engine, autocommit=False, autoflush=False)


@pytest.fixture(autouse=True)
def patch_task_session(sync_session_factory, monkeypatch):
    """Route the pipeline's DB calls to the test database."""
    import app.processing.tasks as task_module
    monkeypatch.setattr(task_module, "_new_session", lambda: sync_session_factory())


# ── dependency mocks ───────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def mock_embed_texts(monkeypatch):
    """Return deterministic fake 1536-dim embeddings without calling OpenAI."""
    def _fake_embed(texts):
        return [[float(i) / 1000.0] * 1536 for i in range(len(texts))]
    monkeypatch.setattr("app.processing.tasks.embed_texts", _fake_embed)


@pytest.fixture
def mock_storage():
    return InMemoryStorage()


@pytest.fixture(autouse=True)
def patch_storage(mock_storage, monkeypatch):
    monkeypatch.setattr("app.processing.tasks.get_storage", lambda: mock_storage)


# ── document fixture ───────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def pipeline_document(
    db_session,
    user_with_token: tuple[User, str],
    mock_storage: InMemoryStorage,
) -> tuple[Document, str]:
    """Upload a plain-text document ready for pipeline processing."""
    from app.domains.schemas import DomainCreateRequest
    from app.domains.service import create_domain
    from app.documents.service import upload_document
    from fastapi import UploadFile
    from starlette.datastructures import Headers

    owner, _ = user_with_token

    domain = await create_domain(
        DomainCreateRequest(name="Pipeline Test Domain"),
        owner.id,
        db_session,
    )

    content = b"First paragraph of content.\n\nSecond paragraph with more details.\n\nThird paragraph."
    upload = UploadFile(
        filename="test.txt",
        file=io.BytesIO(content),
        headers=Headers({"content-type": "text/plain"}),
    )
    doc = await upload_document(
        domain_id=domain.id,
        file=upload,
        title="Pipeline Test Doc",
        owner_id=owner.id,
        storage=mock_storage,
        db=db_session,
    )
    return doc, content.decode()


# ── happy path ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_indexes_document(pipeline_document, sync_session_factory):
    """Full happy path: pending → indexed with correct chunks and embeddings."""
    doc, _ = pipeline_document

    from app.processing.tasks import extract_text
    extract_text.apply(args=(str(doc.id),), throw=False)

    with sync_session_factory() as db:
        refreshed = db.get(Document, doc.id)
        assert refreshed.status == DocumentStatus.indexed.value
        assert refreshed.chunk_count > 0
        assert refreshed.error_message is None

        chunks = db.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
        ).scalars().all()
        assert len(chunks) == refreshed.chunk_count
        assert all(c.embedding is not None for c in chunks)
        assert all(len(c.embedding) == 1536 for c in chunks)


@pytest.mark.asyncio
async def test_pipeline_sets_chunk_indices_sequentially(pipeline_document, sync_session_factory):
    """Chunk indices must be sequential starting from 0."""
    doc, _ = pipeline_document

    from app.processing.tasks import extract_text
    extract_text.apply(args=(str(doc.id),), throw=False)

    with sync_session_factory() as db:
        chunks = db.execute(
            select(DocumentChunk)
            .where(DocumentChunk.document_id == doc.id)
            .order_by(DocumentChunk.chunk_index)
        ).scalars().all()
        indices = [c.chunk_index for c in chunks]
        assert indices == list(range(len(chunks)))


@pytest.mark.asyncio
async def test_pipeline_idempotent_reprocessing(pipeline_document, sync_session_factory):
    """Running the pipeline twice must not duplicate chunks."""
    doc, _ = pipeline_document

    from app.processing.tasks import extract_text
    extract_text.apply(args=(str(doc.id),), throw=False)

    # Reset to pending to allow a second run.
    with sync_session_factory() as db:
        d = db.get(Document, doc.id)
        d.status = DocumentStatus.pending.value
        db.commit()

    extract_text.apply(args=(str(doc.id),), throw=False)

    with sync_session_factory() as db:
        refreshed = db.get(Document, doc.id)
        assert refreshed.status == DocumentStatus.indexed.value
        chunks = db.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
        ).scalars().all()
        # chunk_count must equal actual rows — no duplicates
        assert len(chunks) == refreshed.chunk_count


# ── failure paths ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_marks_failed_on_extraction_error(
    pipeline_document, monkeypatch, sync_session_factory
):
    """An exception in the extract stage must set status=failed with an error message."""
    doc, _ = pipeline_document

    def _raise_extract(*args, **kwargs):
        raise RuntimeError("Simulated extraction failure")

    monkeypatch.setattr("app.processing.tasks._stage_extract", _raise_extract)

    from app.processing.tasks import extract_text
    extract_text.apply(args=(str(doc.id),), throw=False)

    with sync_session_factory() as db:
        refreshed = db.get(Document, doc.id)
        assert refreshed.status == DocumentStatus.failed.value
        assert refreshed.error_message is not None
        assert len(refreshed.error_message) > 0


@pytest.mark.asyncio
async def test_pipeline_empty_text_marks_failed(
    pipeline_document, monkeypatch, sync_session_factory
):
    """If extraction returns empty string, document must be marked failed."""
    doc, _ = pipeline_document

    monkeypatch.setattr("app.processing.tasks._stage_extract", lambda *a, **k: "")

    from app.processing.tasks import extract_text
    extract_text.apply(args=(str(doc.id),), throw=False)

    with sync_session_factory() as db:
        refreshed = db.get(Document, doc.id)
        assert refreshed.status == DocumentStatus.failed.value


# ── guard paths ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_pipeline_skips_soft_deleted_document(
    pipeline_document, sync_session_factory
):
    """Soft-deleted documents must be skipped — status remains pending."""
    doc, _ = pipeline_document

    with sync_session_factory() as db:
        from datetime import datetime, timezone
        d = db.get(Document, doc.id)
        d.deleted_at = datetime.now(timezone.utc)
        db.commit()

    from app.processing.tasks import extract_text
    extract_text.apply(args=(str(doc.id),), throw=False)

    with sync_session_factory() as db:
        refreshed = db.get(Document, doc.id)
        assert refreshed.status == DocumentStatus.pending.value  # unchanged


def test_pipeline_skips_nonexistent_document():
    """Pipeline must not raise for a document_id that does not exist."""
    from app.processing.tasks import extract_text
    extract_text.apply(args=(str(uuid.uuid4()),), throw=False)


@pytest.mark.asyncio
async def test_pipeline_skips_already_processing_document(
    pipeline_document, sync_session_factory
):
    """If status is already 'processing' the task is a no-op (duplicate-run guard)."""
    doc, _ = pipeline_document

    with sync_session_factory() as db:
        d = db.get(Document, doc.id)
        d.status = DocumentStatus.processing.value
        db.commit()

    from app.processing.tasks import extract_text
    extract_text.apply(args=(str(doc.id),), throw=False)

    with sync_session_factory() as db:
        refreshed = db.get(Document, doc.id)
        # Status must remain processing — no chunks created, no failure
        assert refreshed.status == DocumentStatus.processing.value
        chunks = db.execute(
            select(DocumentChunk).where(DocumentChunk.document_id == doc.id)
        ).scalars().all()
        assert len(chunks) == 0
