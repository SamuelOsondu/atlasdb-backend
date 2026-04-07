from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    UserResponse,
)
from app.auth.service import (
    authenticate_user,
    logout_user,
    refresh_access_token,
    register_user,
)
from app.core.dependencies import get_db
from app.core.rate_limit import limiter
from app.shared.schemas import ApiResponse

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/register", response_model=ApiResponse, status_code=201)
async def register(
    body: RegisterRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    user, tokens = await register_user(body, db)
    return ApiResponse(
        success=True,
        data={
            "user": UserResponse.model_validate(user).model_dump(mode="json"),
            "tokens": tokens.model_dump(),
        },
        message="Account created successfully",
    )


@router.post("/login", response_model=ApiResponse)
@limiter.limit("5/minute")
async def login(
    request: Request,
    body: LoginRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    user, tokens = await authenticate_user(body, db)
    return ApiResponse(
        success=True,
        data={
            "user": UserResponse.model_validate(user).model_dump(mode="json"),
            "tokens": tokens.model_dump(),
        },
        message="Login successful",
    )


@router.post("/refresh", response_model=ApiResponse)
async def refresh(
    body: RefreshRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    tokens = await refresh_access_token(body.refresh_token, db)
    return ApiResponse(success=True, data=tokens.model_dump(), message="Token refreshed")


@router.post("/logout", response_model=ApiResponse)
async def logout(
    body: LogoutRequest,
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    await logout_user(body.refresh_token, db)
    return ApiResponse(success=True, data=None, message="Logged out successfully")
