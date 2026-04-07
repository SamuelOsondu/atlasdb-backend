import math
import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppValidationError, NotFoundError
from app.core.security import hash_password, verify_password
from app.users.models import User
from app.users.schemas import UpdateProfileRequest


async def get_user_by_id(user_id: uuid.UUID, db: AsyncSession) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if user is None:
        raise NotFoundError("User not found")
    return user


async def update_user_profile(
    user: User,
    data: UpdateProfileRequest,
    db: AsyncSession,
) -> User:
    fields_set = data.model_fields_set
    updated = False

    # full_name: only touch if explicitly included in the request body.
    # Sending null clears it; omitting it leaves it unchanged.
    if "full_name" in fields_set:
        user.full_name = data.full_name
        updated = True

    if data.current_password is not None and data.new_password is not None:
        if not verify_password(data.current_password, user.hashed_password):
            raise AppValidationError("Current password is incorrect", field="current_password")
        if data.current_password == data.new_password:
            raise AppValidationError(
                "New password must differ from current password", field="new_password"
            )
        user.hashed_password = hash_password(data.new_password)
        updated = True

    if not updated:
        raise AppValidationError("No fields to update")

    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return user


async def list_users(
    page: int,
    page_size: int,
    db: AsyncSession,
) -> tuple[list[User], int]:
    offset = (page - 1) * page_size

    total: int = (await db.execute(select(func.count()).select_from(User))).scalar_one()
    users = list(
        (
            await db.execute(
                select(User).order_by(User.created_at.desc()).offset(offset).limit(page_size)
            )
        ).scalars()
    )
    return users, total


async def set_user_active(user_id: uuid.UUID, is_active: bool, db: AsyncSession) -> User:
    user = await get_user_by_id(user_id, db)
    user.is_active = is_active
    user.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(user)
    return user
