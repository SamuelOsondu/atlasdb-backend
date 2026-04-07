"""
Fixtures shared across documents service and router tests.

Provides:
  - user_with_token      — primary test user + valid JWT
  - other_user_with_token — secondary user (used for ownership-isolation tests)
  - domain               — a KnowledgeDomain owned by user_with_token
  - document             — a Document belonging to that domain
  - mock_storage         — in-memory StorageBackend for file upload tests
"""
import io
import uuid

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import RegisterRequest
from app.auth.service import register_user
from app.documents.models import Document
from app.domains.models import KnowledgeDomain
from app.domains.schemas import DomainCreateRequest
from app.domains.service import create_domain
from app.shared.enums import DocumentStatus
from app.users.models import User


# ── user fixtures ──────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def user_with_token(db_session: AsyncSession) -> tuple[User, str]:
    user, tokens = await register_user(
        RegisterRequest(email="doc_owner@example.com", password="password1"),
        db_session,
    )
    return user, tokens.access_token


@pytest_asyncio.fixture
async def other_user_with_token(db_session: AsyncSession) -> tuple[User, str]:
    user, tokens = await register_user(
        RegisterRequest(email="doc_other@example.com", password="password1"),
        db_session,
    )
    return user, tokens.access_token


@pytest_asyncio.fixture
async def admin_user_with_token(db_session: AsyncSession) -> tuple[User, str]:
    user, tokens = await register_user(
        RegisterRequest(email="doc_admin@example.com", password="password1"),
        db_session,
    )
    user.is_admin = True
    await db_session.commit()
    await db_session.refresh(user)
    return user, tokens.access_token


# ── domain + document fixtures ─────────────────────────────────────────────────

@pytest_asyncio.fixture
async def domain(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
) -> KnowledgeDomain:
    owner, _ = user_with_token
    return await create_domain(
        DomainCreateRequest(name="Test Domain"),
        owner.id,
        db_session,
    )


@pytest_asyncio.fixture
async def document(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
) -> Document:
    owner, _ = user_with_token
    doc = Document(
        owner_id=owner.id,
        domain_id=domain.id,
        title="Test Document",
        original_filename="test.pdf",
        file_key=f"{uuid.uuid4()}",
        file_size=1024,
        mime_type="application/pdf",
        status=DocumentStatus.pending.value,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest_asyncio.fixture
async def indexed_document(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
) -> Document:
    """A document in indexed status (has completed processing)."""
    owner, _ = user_with_token
    doc = Document(
        owner_id=owner.id,
        domain_id=domain.id,
        title="Indexed Document",
        original_filename="indexed.pdf",
        file_key=f"{uuid.uuid4()}",
        file_size=2048,
        mime_type="application/pdf",
        status=DocumentStatus.indexed.value,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


@pytest_asyncio.fixture
async def processing_document(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
) -> Document:
    """A document currently in processing status."""
    owner, _ = user_with_token
    doc = Document(
        owner_id=owner.id,
        domain_id=domain.id,
        title="Processing Document",
        original_filename="processing.pdf",
        file_key=f"{uuid.uuid4()}",
        file_size=512,
        mime_type="application/pdf",
        status=DocumentStatus.processing.value,
    )
    db_session.add(doc)
    await db_session.commit()
    await db_session.refresh(doc)
    return doc


# ── storage fixture ────────────────────────────────────────────────────────────

class InMemoryStorage:
    """Minimal in-memory storage backend for tests — no disk I/O required."""

    def __init__(self):
        self._store: dict[str, bytes] = {}

    async def store(self, content: bytes, filename: str, content_type: str) -> str:
        key = f"{uuid.uuid4()}_{filename}"
        self._store[key] = content
        return key

    async def retrieve(self, key: str) -> bytes:
        return self._store[key]

    async def delete(self, key: str) -> None:
        self._store.pop(key, None)


@pytest_asyncio.fixture
def mock_storage() -> InMemoryStorage:
    return InMemoryStorage()


# ── upload helper ──────────────────────────────────────────────────────────────

def make_upload_bytes(content: bytes = b"fake pdf content") -> tuple[bytes, dict]:
    """Return (raw_bytes, httpx_files_dict) ready for multipart POST."""
    return content, {
        "file": ("test.pdf", io.BytesIO(content), "application/pdf"),
    }
