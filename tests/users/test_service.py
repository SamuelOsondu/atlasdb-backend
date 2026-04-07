import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import RegisterRequest
from app.auth.service import register_user
from app.core.exceptions import AppValidationError, NotFoundError
from app.users.schemas import UpdateProfileRequest
from app.users.service import get_user_by_id, list_users, set_user_active, update_user_profile
import uuid


@pytest.mark.asyncio
async def test_get_user_by_id_returns_user(db_session: AsyncSession):
    user, _ = await register_user(
        RegisterRequest(email="getbyid@example.com", password="password1"), db_session
    )
    fetched = await get_user_by_id(user.id, db_session)
    assert fetched.id == user.id


@pytest.mark.asyncio
async def test_get_user_by_id_raises_not_found(db_session: AsyncSession):
    with pytest.raises(NotFoundError):
        await get_user_by_id(uuid.uuid4(), db_session)


@pytest.mark.asyncio
async def test_update_profile_updates_full_name(db_session: AsyncSession):
    user, _ = await register_user(
        RegisterRequest(email="updatename@example.com", password="password1", full_name="Old"),
        db_session,
    )
    updated = await update_user_profile(
        user, UpdateProfileRequest.model_validate({"full_name": "New Name"}), db_session
    )
    assert updated.full_name == "New Name"


@pytest.mark.asyncio
async def test_update_profile_clears_full_name(db_session: AsyncSession):
    user, _ = await register_user(
        RegisterRequest(email="clearname@example.com", password="password1", full_name="Has Name"),
        db_session,
    )
    updated = await update_user_profile(
        user, UpdateProfileRequest.model_validate({"full_name": None}), db_session
    )
    assert updated.full_name is None


@pytest.mark.asyncio
async def test_update_profile_omitting_full_name_leaves_it_unchanged(db_session: AsyncSession):
    user, _ = await register_user(
        RegisterRequest(email="unchanged@example.com", password="password1", full_name="Keep Me"),
        db_session,
    )
    # Provide only a password change — full_name must remain untouched
    updated = await update_user_profile(
        user,
        UpdateProfileRequest.model_validate(
            {"current_password": "password1", "new_password": "newpassword1"}
        ),
        db_session,
    )
    assert updated.full_name == "Keep Me"


@pytest.mark.asyncio
async def test_update_profile_changes_password(db_session: AsyncSession):
    user, _ = await register_user(
        RegisterRequest(email="changepwd@example.com", password="oldpassword"),
        db_session,
    )
    old_hash = user.hashed_password
    await update_user_profile(
        user,
        UpdateProfileRequest.model_validate(
            {"current_password": "oldpassword", "new_password": "newpassword"}
        ),
        db_session,
    )
    assert user.hashed_password != old_hash


@pytest.mark.asyncio
async def test_update_profile_rejects_wrong_current_password(db_session: AsyncSession):
    user, _ = await register_user(
        RegisterRequest(email="wrongpwd@example.com", password="correctpass"),
        db_session,
    )
    with pytest.raises(AppValidationError) as exc_info:
        await update_user_profile(
            user,
            UpdateProfileRequest.model_validate(
                {"current_password": "wrongpass", "new_password": "newpassword"}
            ),
            db_session,
        )
    assert exc_info.value.field == "current_password"


@pytest.mark.asyncio
async def test_update_profile_rejects_same_new_password(db_session: AsyncSession):
    user, _ = await register_user(
        RegisterRequest(email="samepwd@example.com", password="mypassword"),
        db_session,
    )
    with pytest.raises(AppValidationError) as exc_info:
        await update_user_profile(
            user,
            UpdateProfileRequest.model_validate(
                {"current_password": "mypassword", "new_password": "mypassword"}
            ),
            db_session,
        )
    assert exc_info.value.field == "new_password"


@pytest.mark.asyncio
async def test_update_profile_raises_if_nothing_to_update(db_session: AsyncSession):
    user, _ = await register_user(
        RegisterRequest(email="nothing@example.com", password="password1"),
        db_session,
    )
    with pytest.raises(AppValidationError):
        # Empty body — model_fields_set will be empty, no password pair either
        await update_user_profile(user, UpdateProfileRequest(), db_session)


@pytest.mark.asyncio
async def test_list_users_returns_all_users(db_session: AsyncSession):
    await register_user(
        RegisterRequest(email="list1@example.com", password="password1"), db_session
    )
    await register_user(
        RegisterRequest(email="list2@example.com", password="password1"), db_session
    )
    users, total = await list_users(page=1, page_size=100, db=db_session)
    assert total >= 2
    assert len(users) >= 2


@pytest.mark.asyncio
async def test_list_users_respects_pagination(db_session: AsyncSession):
    for i in range(5):
        await register_user(
            RegisterRequest(email=f"page{i}@example.com", password="password1"), db_session
        )
    users, total = await list_users(page=1, page_size=2, db=db_session)
    assert len(users) == 2
    assert total >= 5


@pytest.mark.asyncio
async def test_set_user_active_deactivates(db_session: AsyncSession):
    user, _ = await register_user(
        RegisterRequest(email="deactivate@example.com", password="password1"), db_session
    )
    updated = await set_user_active(user.id, is_active=False, db=db_session)
    assert updated.is_active is False


@pytest.mark.asyncio
async def test_set_user_active_reactivates(db_session: AsyncSession):
    user, _ = await register_user(
        RegisterRequest(email="reactivate@example.com", password="password1"), db_session
    )
    await set_user_active(user.id, is_active=False, db=db_session)
    updated = await set_user_active(user.id, is_active=True, db=db_session)
    assert updated.is_active is True


@pytest.mark.asyncio
async def test_set_user_active_raises_not_found(db_session: AsyncSession):
    with pytest.raises(NotFoundError):
        await set_user_active(uuid.uuid4(), is_active=False, db=db_session)
