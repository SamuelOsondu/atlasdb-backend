import pytest_asyncio
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import RegisterRequest
from app.auth.service import register_user
from app.domains.schemas import DomainCreateRequest
from app.domains.service import create_domain
from app.domains.models import KnowledgeDomain
from app.users.models import User


@pytest_asyncio.fixture
async def user_with_token(db_session: AsyncSession) -> tuple[User, str]:
    user, tokens = await register_user(
        RegisterRequest(email="domainowner@example.com", password="password1"),
        db_session,
    )
    return user, tokens.access_token


@pytest_asyncio.fixture
async def other_user_with_token(db_session: AsyncSession) -> tuple[User, str]:
    user, tokens = await register_user(
        RegisterRequest(email="otherowner@example.com", password="password1"),
        db_session,
    )
    return user, tokens.access_token


@pytest_asyncio.fixture
async def domain(db_session: AsyncSession, user_with_token: tuple[User, str]) -> KnowledgeDomain:
    owner, _ = user_with_token
    return await create_domain(
        DomainCreateRequest(name="Engineering Docs", description="Internal engineering knowledge"),
        owner.id,
        db_session,
    )
