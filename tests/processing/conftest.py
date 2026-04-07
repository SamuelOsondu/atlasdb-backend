"""
Fixtures for processing pipeline tests.

Uses distinct email addresses from other test modules to prevent unique-constraint
violations when the full test suite runs in a single pytest session.
"""
import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import RegisterRequest
from app.auth.service import register_user
from app.users.models import User
from tests.documents.conftest import InMemoryStorage  # noqa: F401 — re-export for test_tasks


@pytest_asyncio.fixture
async def user_with_token(db_session: AsyncSession) -> tuple[User, str]:
    user, tokens = await register_user(
        RegisterRequest(email="pipeline_owner@example.com", password="password1"),
        db_session,
    )
    return user, tokens.access_token


@pytest_asyncio.fixture
async def other_user_with_token(db_session: AsyncSession) -> tuple[User, str]:
    user, tokens = await register_user(
        RegisterRequest(email="pipeline_other@example.com", password="password1"),
        db_session,
    )
    return user, tokens.access_token
