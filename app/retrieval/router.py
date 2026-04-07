"""
Retrieval router — semantic search endpoint.

POST /api/v1/search
  Body: SearchRequest (query, optional domain_id, optional top_k)
  Returns: ApiResponse wrapping SearchResponse (results list + total count)
"""
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_user, get_db
from app.retrieval.schemas import SearchRequest, SearchResponse
from app.retrieval.service import search
from app.shared.schemas import ApiResponse
from app.users.models import User

router = APIRouter(tags=["search"])


@router.post("/search", response_model=ApiResponse)
async def search_endpoint(
    body: SearchRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    """
    Semantic search over the caller's indexed documents.

    - If `domain_id` is provided, search is scoped to that domain (must be owned by caller).
    - Results are ordered by cosine similarity, highest first.
    - Chunks below the configured similarity threshold are excluded.
    - Returns an empty results list (not an error) when no matches are found.
    """
    results = await search(
        query=body.query,
        user_id=current_user.id,
        domain_id=body.domain_id,
        top_k=body.top_k,
        db=db,
    )
    response_data = SearchResponse(results=results, total=len(results))
    return ApiResponse(
        success=True,
        data=response_data.model_dump(mode="json"),
        message="Search completed successfully",
    )
