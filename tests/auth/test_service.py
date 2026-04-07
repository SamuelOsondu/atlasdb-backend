import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import LoginRequest, RegisterRequest
from app.auth.service import (
    authenticate_user,
    logout_user,
    refresh_access_token,
    register_user,
)
from app.core.exceptions import AuthenticationError, ConflictError
from app.core.security import decode_access_token, hash_refresh_token


@pytest.mark.asyncio
async def test_register_creates_user_and_issues_tokens(db_session: AsyncSession):
    data = RegisterRequest(email="alice@example.com", password="securepass", full_name="Alice")
    user, tokens = await register_user(data, db_session)

    assert user.id is not None
    assert user.email == "alice@example.com"
    assert user.full_name == "Alice"
    assert user.hashed_password != "securepass"  # must be hashed
    assert tokens.access_token
    assert tokens.refresh_token
    assert tokens.token_type == "bearer"


@pytest.mark.asyncio
async def test_register_hashes_password(db_session: AsyncSession):
    data = RegisterRequest(email="bob@example.com", password="mypassword1")
    user, _ = await register_user(data, db_session)
    assert user.hashed_password != "mypassword1"
    assert user.hashed_password.startswith("$2b$")


@pytest.mark.asyncio
async def test_register_rejects_duplicate_email(db_session: AsyncSession):
    data = RegisterRequest(email="duplicate@example.com", password="password1")
    await register_user(data, db_session)

    with pytest.raises(ConflictError):
        await register_user(
            RegisterRequest(email="duplicate@example.com", password="password2"),
            db_session,
        )


@pytest.mark.asyncio
async def test_register_normalizes_email(db_session: AsyncSession):
    data = RegisterRequest(email="UPPER@EXAMPLE.COM", password="password1")
    user, _ = await register_user(data, db_session)
    assert user.email == "upper@example.com"


@pytest.mark.asyncio
async def test_login_succeeds_with_correct_credentials(db_session: AsyncSession):
    await register_user(
        RegisterRequest(email="loginok@example.com", password="correctpass"),
        db_session,
    )
    user, tokens = await authenticate_user(
        LoginRequest(email="loginok@example.com", password="correctpass"),
        db_session,
    )
    assert user.email == "loginok@example.com"
    assert tokens.access_token


@pytest.mark.asyncio
async def test_login_fails_with_wrong_password(db_session: AsyncSession):
    await register_user(
        RegisterRequest(email="wrongpass@example.com", password="correctpass"),
        db_session,
    )
    with pytest.raises(AuthenticationError):
        await authenticate_user(
            LoginRequest(email="wrongpass@example.com", password="wrongpass"),
            db_session,
        )


@pytest.mark.asyncio
async def test_login_fails_for_nonexistent_user(db_session: AsyncSession):
    with pytest.raises(AuthenticationError):
        await authenticate_user(
            LoginRequest(email="ghost@example.com", password="doesnotmatter"),
            db_session,
        )


@pytest.mark.asyncio
async def test_access_token_encodes_user_id(db_session: AsyncSession):
    data = RegisterRequest(email="tokencheck@example.com", password="password1")
    user, tokens = await register_user(data, db_session)
    user_id_from_token = decode_access_token(tokens.access_token)
    assert user_id_from_token == str(user.id)


@pytest.mark.asyncio
async def test_refresh_token_not_stored_raw(db_session: AsyncSession):
    from sqlalchemy import select
    from app.auth.models import RefreshToken

    data = RegisterRequest(email="rawcheck@example.com", password="password1")
    _, tokens = await register_user(data, db_session)

    result = await db_session.execute(select(RefreshToken))
    stored_tokens = result.scalars().all()
    raw = tokens.refresh_token

    for stored in stored_tokens:
        assert stored.token_hash != raw  # raw token must never be stored


@pytest.mark.asyncio
async def test_refresh_issues_new_tokens_and_rotates(db_session: AsyncSession):
    _, original_tokens = await register_user(
        RegisterRequest(email="rotate@example.com", password="password1"),
        db_session,
    )
    new_tokens = await refresh_access_token(original_tokens.refresh_token, db_session)

    assert new_tokens.access_token != original_tokens.access_token
    assert new_tokens.refresh_token != original_tokens.refresh_token

    # Old refresh token must now be rejected
    with pytest.raises(AuthenticationError):
        await refresh_access_token(original_tokens.refresh_token, db_session)


@pytest.mark.asyncio
async def test_refresh_rejects_invalid_token(db_session: AsyncSession):
    with pytest.raises(AuthenticationError):
        await refresh_access_token("completely_invalid_token", db_session)


@pytest.mark.asyncio
async def test_logout_revokes_refresh_token(db_session: AsyncSession):
    _, tokens = await register_user(
        RegisterRequest(email="logout@example.com", password="password1"),
        db_session,
    )
    await logout_user(tokens.refresh_token, db_session)

    # Token should now be rejected on refresh
    with pytest.raises(AuthenticationError):
        await refresh_access_token(tokens.refresh_token, db_session)


@pytest.mark.asyncio
async def test_logout_is_idempotent(db_session: AsyncSession):
    _, tokens = await register_user(
        RegisterRequest(email="idempotent@example.com", password="password1"),
        db_session,
    )
    # Calling logout twice must not raise
    await logout_user(tokens.refresh_token, db_session)
    await logout_user(tokens.refresh_token, db_session)


@pytest.mark.asyncio
async def test_multiple_devices_each_have_independent_tokens(db_session: AsyncSession):
    await register_user(
        RegisterRequest(email="multidevice@example.com", password="password1"),
        db_session,
    )
    _, tokens_device_a = await authenticate_user(
        LoginRequest(email="multidevice@example.com", password="password1"),
        db_session,
    )
    _, tokens_device_b = await authenticate_user(
        LoginRequest(email="multidevice@example.com", password="password1"),
        db_session,
    )
    assert tokens_device_a.refresh_token != tokens_device_b.refresh_token

    # Logging out device A does not affect device B
    await logout_user(tokens_device_a.refresh_token, db_session)
    new_tokens = await refresh_access_token(tokens_device_b.refresh_token, db_session)
    assert new_tokens.access_token
