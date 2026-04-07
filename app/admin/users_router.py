import math
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_admin
from app.core.exceptions import AppValidationError
from app.shared.schemas import ApiResponse, PaginatedResponse, PaginationMeta
from app.users.models import User
from app.users.schemas import UserResponse
from app.users.service import list_users, set_user_active

router = APIRouter(prefix="/admin/users", tags=["admin"])


@router.get("", response_model=PaginatedResponse)
async def list_all_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    users, total = await list_users(page, page_size, db)
    total_pages = max(1, math.ceil(total / page_size))
    return PaginatedResponse(
        success=True,
        data=[UserResponse.model_validate(u).model_dump(mode="json") for u in users],
        message="Users retrieved",
        pagination=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
    )


@router.patch("/{user_id}/deactivate", response_model=ApiResponse)
async def deactivate_user(
    user_id: uuid.UUID,
    current_admin: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    if user_id == current_admin.id:
        raise AppValidationError("Cannot deactivate your own account")
    user = await set_user_active(user_id, is_active=False, db=db)
    return ApiResponse(
        success=True,
        data=UserResponse.model_validate(user).model_dump(mode="json"),
        message="User deactivated",
    )


@router.patch("/{user_id}/reactivate", response_model=ApiResponse)
async def reactivate_user(
    user_id: uuid.UUID,
    _: User = Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    user = await set_user_active(user_id, is_active=True, db=db)
    return ApiResponse(
        success=True,
        data=UserResponse.model_validate(user).model_dump(mode="json"),
        message="User reactivated",
    )
