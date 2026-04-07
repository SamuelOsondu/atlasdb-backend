"""
Documents router — file upload, listing, detail, and soft delete.

Upload endpoint uses multipart/form-data via FastAPI UploadFile + Form.
All non-upload routes use JSON responses wrapped in ApiResponse / PaginatedResponse.
"""
import math
import uuid

from fastapi import APIRouter, Depends, Form, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db, get_storage_dep
from app.core.storage import StorageBackend
from app.documents.schemas import DocumentListResponse, DocumentResponse
from app.documents.service import (
    get_document_or_404,
    list_documents,
    soft_delete_document,
    upload_document,
)
from app.shared.schemas import ApiResponse, PaginatedResponse, PaginationMeta
from app.users.models import User

router = APIRouter(tags=["documents"])


# ── POST /domains/{domain_id}/documents ────────────────────────────────────────

@router.post(
    "/domains/{domain_id}/documents",
    response_model=ApiResponse,
    status_code=201,
)
async def upload_document_endpoint(
    domain_id: uuid.UUID,
    file: UploadFile,
    title: str | None = Form(default=None),
    current_user: User = Depends(get_current_user),
    storage: StorageBackend = Depends(get_storage_dep),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    doc = await upload_document(
        domain_id=domain_id,
        file=file,
        title=title,
        owner_id=current_user.id,
        storage=storage,
        db=db,
    )
    data = DocumentResponse.model_validate(doc)
    return ApiResponse(success=True, data=data.model_dump(mode="json"), message="Document uploaded successfully")


# ── GET /domains/{domain_id}/documents ─────────────────────────────────────────

@router.get(
    "/domains/{domain_id}/documents",
    response_model=PaginatedResponse,
)
async def list_documents_endpoint(
    domain_id: uuid.UUID,
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    docs, total = await list_documents(
        domain_id=domain_id,
        owner_id=current_user.id,
        page=page,
        page_size=page_size,
        db=db,
    )
    items = [DocumentListResponse.model_validate(d).model_dump(mode="json") for d in docs]
    return PaginatedResponse(
        success=True,
        data=items,
        message="Documents retrieved successfully",
        pagination=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=max(1, math.ceil(total / page_size)),
        ),
    )


# ── GET /documents/{document_id} ───────────────────────────────────────────────

@router.get(
    "/documents/{document_id}",
    response_model=ApiResponse,
)
async def get_document_endpoint(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    doc = await get_document_or_404(document_id, current_user.id, db)
    data = DocumentResponse.model_validate(doc)
    return ApiResponse(success=True, data=data.model_dump(mode="json"), message="Document retrieved successfully")


# ── DELETE /documents/{document_id} ────────────────────────────────────────────

@router.delete(
    "/documents/{document_id}",
    response_model=ApiResponse,
)
async def delete_document_endpoint(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    doc = await get_document_or_404(document_id, current_user.id, db)
    await soft_delete_document(doc, db)
    return ApiResponse(success=True, data=None, message="Document deleted successfully")
