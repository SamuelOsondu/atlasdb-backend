from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.shared.schemas import ApiResponse
from app.users.models import User
from app.users.schemas import UpdateProfileRequest, UserResponse
from app.users.service import update_user_profile

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/me", response_model=ApiResponse)
async def get_my_profile(
    current_user: User = Depends(get_current_user),
) -> ApiResponse:
    return ApiResponse(
        success=True,
        data=UserResponse.model_validate(current_user).model_dump(mode="json"),
        message="Profile retrieved",
    )


@router.patch("/me", response_model=ApiResponse)
async def update_my_profile(
    body: UpdateProfileRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    user = await update_user_profile(current_user, body, db)
    return ApiResponse(
        success=True,
        data=UserResponse.model_validate(user).model_dump(mode="json"),
        message="Profile updated",
    )
