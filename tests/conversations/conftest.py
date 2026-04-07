"""
Fixtures for conversations tests.

Uses distinct email addresses from other test modules to prevent unique-constraint
violations when the full test suite runs in a single pytest session.
"""
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import RegisterRequest
from app.auth.service import register_user
from app.conversations.models import Conversation
from app.conversations.schemas import ConversationCreateRequest
from app.conversations.service import append_message, create_conversation
from app.domains.models import KnowledgeDomain
from app.domains.schemas import DomainCreateRequest
from app.domains.service import create_domain
from app.shared.enums import MessageRole
from app.users.models import User


@pytest_asyncio.fixture
async def user_with_token(db_session: AsyncSession) -> tuple[User, str]:
    user, tokens = await register_user(
        RegisterRequest(email="conv_owner@example.com", password="password1"),
        db_session,
    )
    return user, tokens.access_token


@pytest_asyncio.fixture
async def other_user_with_token(db_session: AsyncSession) -> tuple[User, str]:
    user, tokens = await register_user(
        RegisterRequest(email="conv_other@example.com", password="password1"),
        db_session,
    )
    return user, tokens.access_token


@pytest_asyncio.fixture
async def domain(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
) -> KnowledgeDomain:
    owner, _ = user_with_token
    return await create_domain(
        DomainCreateRequest(name="Conv Test Domain"),
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
        DomainCreateRequest(name="Other Conv Domain"),
        owner.id,
        db_session,
    )


@pytest_asyncio.fixture
async def conversation(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
) -> Conversation:
    owner, _ = user_with_token
    return await create_conversation(
        ConversationCreateRequest(title="Test Conversation"),
        owner.id,
        db_session,
    )


@pytest_asyncio.fixture
async def conversation_with_messages(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    conversation: Conversation,
) -> Conversation:
    """A conversation with two messages (user + assistant)."""
    await append_message(
        conversation,
        MessageRole.user,
        "What is the capital of France?",
        None,
        db_session,
    )
    await append_message(
        conversation,
        MessageRole.assistant,
        "The capital of France is Paris.",
        [{"doc_id": "00000000-0000-0000-0000-000000000001",
          "doc_title": "Europe Guide",
          "chunk_index": 0,
          "excerpt": "Paris is the capital..."}],
        db_session,
    )
    await db_session.refresh(conversation)
    return conversation
