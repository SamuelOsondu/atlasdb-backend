"""
Shared test fixtures for AtlasDB.

Isolation strategy
------------------
Services call ``session.commit()`` to persist data. A simple rollback after
each test would be a no-op for already-committed rows and leave stale data.

Instead we use SQLAlchemy 2.0's ``join_transaction_mode="create_savepoint"``:

1. Each test opens a real connection and begins an outer transaction.
2. The session joins that connection with ``create_savepoint`` mode, so every
   ``session.commit()`` inside production code becomes a savepoint release,
   not a true COMMIT.
3. After the test, ``conn.rollback()`` on the outer transaction rolls back all
   savepoints and leaves the database completely clean.
"""
import os
import uuid

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncSession, create_async_engine

from app.core.database import Base
from app.core.dependencies import get_db
from app.core.security import hash_password

# Import models so Base.metadata registers their tables before create_all.
from app.users.models import User  # noqa: F401
from app.auth.models import RefreshToken  # noqa: F401
from app.domains.models import KnowledgeDomain  # noqa: F401
from app.documents.models import Document, DocumentChunk  # noqa: F401
from app.conversations.models import Conversation, Message  # noqa: F401

TEST_DATABASE_URL = os.getenv(
    "TEST_DATABASE_URL",
    "postgresql+asyncpg://postgres:postgres@localhost:5432/atlasdb_test",
)

test_engine = create_async_engine(TEST_DATABASE_URL, echo=False)


# ── Schema setup (runs once per test session) ─────────────────────────────────

@pytest_asyncio.fixture(scope="session", autouse=True)
async def setup_database():
    async with test_engine.begin() as conn:
        await conn.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))
        await conn.run_sync(Base.metadata.drop_all)
        await conn.run_sync(Base.metadata.create_all)
    yield
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.drop_all)


# ── Per-test connection with outer transaction ────────────────────────────────

@pytest_asyncio.fixture
async def db_connection() -> AsyncConnection:
    async with test_engine.connect() as conn:
        await conn.begin()
        yield conn
        await conn.rollback()


# ── Per-test session with savepoint isolation ─────────────────────────────────

@pytest_asyncio.fixture
async def db_session(db_connection: AsyncConnection) -> AsyncSession:
    session = AsyncSession(
        bind=db_connection,
        expire_on_commit=False,
        autoflush=False,
        join_transaction_mode="create_savepoint",
    )
    try:
        yield session
    finally:
        await session.close()


# ── App HTTP client ───────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def client(db_session: AsyncSession):
    from app.main import app

    async def override_get_db():
        yield db_session

    app.dependency_overrides[get_db] = override_get_db
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    app.dependency_overrides.clear()


# ── Reusable user fixtures ────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def test_user(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="user@example.com",
        hashed_password=hash_password("Password1!"),
        full_name="Test User",
        is_active=True,
        is_admin=False,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user


@pytest_asyncio.fixture
async def test_admin(db_session: AsyncSession) -> User:
    user = User(
        id=uuid.uuid4(),
        email="admin@example.com",
        hashed_password=hash_password("AdminPass1!"),
        full_name="Admin User",
        is_active=True,
        is_admin=True,
    )
    db_session.add(user)
    await db_session.flush()
    await db_session.refresh(user)
    return user
