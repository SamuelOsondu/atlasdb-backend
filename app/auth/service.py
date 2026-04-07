from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.models import RefreshToken
from app.auth.schemas import LoginRequest, RegisterRequest, TokenResponse
from app.core.config import settings
from app.core.exceptions import AuthenticationError, ConflictError, ForbiddenError
from app.core.security import (
    create_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)
from app.users.models import User

# A real bcrypt hash computed once at startup. Used to keep login timing constant when the user
# does not exist — prevents email enumeration via response time differences.
_DUMMY_HASH: str = hash_password("atlasdb_dummy_timing_prevention")


async def register_user(data: RegisterRequest, db: AsyncSession) -> tuple[User, TokenResponse]:
    result = await db.execute(select(User).where(User.email == data.email))
    if result.scalar_one_or_none() is not None:
        raise ConflictError("An account with this email already exists")

    user = User(
        email=data.email,
        hashed_password=hash_password(data.password),
        full_name=data.full_name,
    )
    db.add(user)

    try:
        await db.flush()  # get user.id; raises IntegrityError on duplicate (race condition)
        tokens = await _issue_tokens(user, db)
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError("An account with this email already exists")

    return user, tokens


async def authenticate_user(data: LoginRequest, db: AsyncSession) -> tuple[User, TokenResponse]:
    result = await db.execute(select(User).where(User.email == data.email))
    user = result.scalar_one_or_none()

    # Always run verify_password to prevent timing-based email enumeration.
    candidate_hash = user.hashed_password if user else _DUMMY_HASH
    password_valid = verify_password(data.password, candidate_hash)

    if user is None or not password_valid:
        raise AuthenticationError("Invalid credentials")

    if not user.is_active:
        raise ForbiddenError("Account is inactive")

    tokens = await _issue_tokens(user, db)
    await db.commit()
    return user, tokens


async def refresh_access_token(raw_refresh_token: str, db: AsyncSession) -> TokenResponse:
    token_hash = hash_refresh_token(raw_refresh_token)

    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()

    if not stored or stored.revoked or stored.expires_at <= datetime.now(timezone.utc):
        raise AuthenticationError("Invalid or expired refresh token")

    result = await db.execute(select(User).where(User.id == stored.user_id))
    user = result.scalar_one_or_none()

    if not user or not user.is_active:
        raise AuthenticationError("Invalid or expired refresh token")

    # Token rotation: revoke old token, issue new pair
    stored.revoked = True
    tokens = await _issue_tokens(user, db)
    await db.commit()
    return tokens


async def logout_user(raw_refresh_token: str, db: AsyncSession) -> None:
    token_hash = hash_refresh_token(raw_refresh_token)
    result = await db.execute(
        select(RefreshToken).where(RefreshToken.token_hash == token_hash)
    )
    stored = result.scalar_one_or_none()

    # Idempotent: revoking an already-revoked or non-existent token is a no-op.
    if stored and not stored.revoked:
        stored.revoked = True
        await db.commit()


async def _issue_tokens(user: User, db: AsyncSession) -> TokenResponse:
    access_token = create_access_token(str(user.id))
    raw_refresh = generate_refresh_token()

    refresh_record = RefreshToken(
        user_id=user.id,
        token_hash=hash_refresh_token(raw_refresh),
        expires_at=datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS),
    )
    db.add(refresh_record)
    await db.flush()

    return TokenResponse(access_token=access_token, refresh_token=raw_refresh)
