"""
Fixtures for query_engine tests.

Uses distinct email addresses (qe_owner@example.com, qe_other@example.com)
to prevent unique-constraint violations when the full suite runs in a single
pytest session.

Provides:
  - user_with_token / other_user_with_token
  - domain
  - conversation (no messages, no domain scope)
  - conversation_in_domain (scoped to `domain`)
  - fake_redis  — in-process Redis stub, no network required
  - SAMPLE_CHUNKS — pre-built SearchResult list for mocking retrieval
"""
import uuid

import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import RegisterRequest
from app.auth.service import register_user
from app.conversations.models import Conversation
from app.conversations.schemas import ConversationCreateRequest
from app.conversations.service import create_conversation
from app.domains.models import KnowledgeDomain
from app.domains.schemas import DomainCreateRequest
from app.domains.service import create_domain
from app.retrieval.schemas import SearchResult
from app.users.models import User

# ── Fake Redis ────────────────────────────────────────────────────────────────

class FakeRedis:
    """Minimal async Redis stub that satisfies the query engine's needs."""

    def __init__(self, should_cancel: bool = False) -> None:
        self._store: dict[str, str] = {}
        self._should_cancel = should_cancel

    async def setex(self, key: str, ttl: int, value: str) -> None:
        self._store[key] = value

    async def exists(self, *keys: str) -> int:
        if self._should_cancel:
            return 1
        return sum(1 for k in keys if k in self._store)

    async def delete(self, *keys: str) -> int:
        count = sum(1 for k in keys if k in self._store)
        for k in keys:
            self._store.pop(k, None)
        return count


# ── Sample data ───────────────────────────────────────────────────────────────

_DOC_ID = uuid.UUID("00000000-0000-0000-0000-000000000099")
_DOMAIN_ID = uuid.UUID("00000000-0000-0000-0000-000000000088")

SAMPLE_CHUNKS: list[SearchResult] = [
    SearchResult(
        chunk_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
        document_id=_DOC_ID,
        domain_id=_DOMAIN_ID,
        document_title="Europe Travel Guide",
        chunk_index=0,
        text="Paris is the capital of France and one of the most visited cities in the world.",
        score=0.92,
    ),
    SearchResult(
        chunk_id=uuid.UUID("00000000-0000-0000-0000-000000000002"),
        document_id=_DOC_ID,
        domain_id=_DOMAIN_ID,
        document_title="Europe Travel Guide",
        chunk_index=1,
        text="The Eiffel Tower is a wrought-iron lattice tower on the Champ de Mars in Paris.",
        score=0.85,
    ),
]

# ── Auth fixtures ─────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def user_with_token(db_session: AsyncSession) -> tuple[User, str]:
    user, tokens = await register_user(
        RegisterRequest(email="qe_owner@example.com", password="password1"),
        db_session,
    )
    return user, tokens.access_token


@pytest_asyncio.fixture
async def other_user_with_token(db_session: AsyncSession) -> tuple[User, str]:
    user, tokens = await register_user(
        RegisterRequest(email="qe_other@example.com", password="password1"),
        db_session,
    )
    return user, tokens.access_token


# ── Domain fixtures ───────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def domain(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
) -> KnowledgeDomain:
    owner, _ = user_with_token
    return await create_domain(
        DomainCreateRequest(name="QE Test Domain"),
        owner.id,
        db_session,
    )


# ── Conversation fixtures ─────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def conversation(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
) -> Conversation:
    owner, _ = user_with_token
    return await create_conversation(
        ConversationCreateRequest(title="QE Test Conversation"),
        owner.id,
        db_session,
    )


@pytest_asyncio.fixture
async def conversation_in_domain(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
) -> Conversation:
    owner, _ = user_with_token
    return await create_conversation(
        ConversationCreateRequest(domain_id=domain.id),
        owner.id,
        db_session,
    )


# ── Redis fixture ─────────────────────────────────────────────────────────────

@pytest_asyncio.fixture
async def fake_redis() -> FakeRedis:
    return FakeRedis()
