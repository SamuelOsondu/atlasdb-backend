import math
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.domains.schemas import DomainCreateRequest, DomainResponse, DomainUpdateRequest
from app.domains.service import (
    create_domain,
    delete_domain,
    get_domain_or_404,
    list_domains,
    update_domain,
)
from app.shared.schemas import ApiResponse, PaginatedResponse, PaginationMeta
from app.users.models import User

router = APIRouter(prefix="/domains", tags=["domains"])


@router.post("", response_model=ApiResponse, status_code=201)
async def create(
    body: DomainCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    domain = await create_domain(body, current_user.id, db)
    return ApiResponse(
        success=True,
        data=DomainResponse.model_validate(domain).model_dump(mode="json"),
        message="Domain created",
    )


@router.get("", response_model=PaginatedResponse)
async def list_my_domains(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    domains, total = await list_domains(current_user.id, page, page_size, db)
    total_pages = max(1, math.ceil(total / page_size))
    return PaginatedResponse(
        success=True,
        data=[DomainResponse.model_validate(d).model_dump(mode="json") for d in domains],
        message="Domains retrieved",
        pagination=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
        ),
    )


@router.get("/{domain_id}", response_model=ApiResponse)
async def get_domain(
    domain_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    domain = await get_domain_or_404(domain_id, current_user.id, db)
    return ApiResponse(
        success=True,
        data=DomainResponse.model_validate(domain).model_dump(mode="json"),
        message="Domain retrieved",
    )


@router.patch("/{domain_id}", response_model=ApiResponse)
async def update(
    domain_id: uuid.UUID,
    body: DomainUpdateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    domain = await get_domain_or_404(domain_id, current_user.id, db)
    updated = await update_domain(domain, body, db)
    return ApiResponse(
        success=True,
        data=DomainResponse.model_validate(updated).model_dump(mode="json"),
        message="Domain updated",
    )


@router.delete("/{domain_id}", response_model=ApiResponse)
async def delete(
    domain_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    domain = await get_domain_or_404(domain_id, current_user.id, db)
    await delete_domain(domain, db)
    return ApiResponse(success=True, data=None, message="Domain deleted")
