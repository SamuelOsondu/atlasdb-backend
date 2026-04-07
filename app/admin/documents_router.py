"""
Admin documents router — reprocessing endpoint.

Requires admin privilege. Resets a document to pending status, clears all
existing chunks, and re-enqueues the processing pipeline job.
"""
import uuid

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_db, require_admin
from app.documents.schemas import DocumentResponse
from app.documents.service import get_any_document_or_404, reprocess_document
from app.shared.schemas import ApiResponse

router = APIRouter(prefix="/admin/documents", tags=["admin", "documents"])


@router.post(
    "/{document_id}/reprocess",
    response_model=ApiResponse,
)
async def reprocess_document_endpoint(
    document_id: uuid.UUID,
    _admin=Depends(require_admin),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """
    Reset a document to `pending` status, clear its chunks, and re-enqueue
    the processing pipeline. Available to admins only.
    """
    doc = await get_any_document_or_404(document_id, db)
    doc = await reprocess_document(doc, db)
    data = DocumentResponse.model_validate(doc)
    return ApiResponse(
        success=True,
        data=data.model_dump(mode="json"),
        message="Document queued for reprocessing",
    )
