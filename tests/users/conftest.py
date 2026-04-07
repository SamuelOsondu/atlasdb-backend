import pytest_asyncio
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import RegisterRequest
from app.auth.service import register_user
from app.users.models import User


@pytest_asyncio.fixture
async def regular_user(db_session: AsyncSession) -> tuple[User, str]:
    """Returns (user, access_token)."""
    user, tokens = await register_user(
        RegisterRequest(email="user@example.com", password="password1", full_name="Regular User"),
        db_session,
    )
    return user, tokens.access_token


@pytest_asyncio.fixture
async def admin_user(db_session: AsyncSession) -> tuple[User, str]:
    """Returns (admin_user, access_token). Sets is_admin=True directly."""
    user, tokens = await register_user(
        RegisterRequest(email="admin@example.com", password="password1", full_name="Admin User"),
        db_session,
    )
    user.is_admin = True
    await db_session.commit()
    await db_session.refresh(user)
    return user, tokens.access_token


@pytest_asyncio.fixture
async def second_user(db_session: AsyncSession) -> tuple[User, str]:
    """A second regular user, used to test cross-user access prevention."""
    user, tokens = await register_user(
        RegisterRequest(email="second@example.com", password="password1"),
        db_session,
    )
    return user, tokens.access_token
