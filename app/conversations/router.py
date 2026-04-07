"""
Conversations router.

Endpoints implemented here (query execution lives in query_engine):
  POST   /api/v1/conversations                              — create conversation
  GET    /api/v1/conversations                              — list (paginated, newest-first)
  GET    /api/v1/conversations/{conversation_id}            — get detail
  DELETE /api/v1/conversations/{conversation_id}            — hard delete
  GET    /api/v1/conversations/{conversation_id}/messages   — message history (cursor-paginated)
"""
import math
import uuid

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.conversations.schemas import (
    ConversationCreateRequest,
    ConversationResponse,
    MessagePageResponse,
    MessageResponse,
)
from app.conversations.service import (
    create_conversation,
    delete_conversation,
    get_conversation_or_404,
    get_messages,
    list_conversations,
)
from app.core.dependencies import get_current_user, get_db
from app.shared.schemas import ApiResponse, PaginatedResponse, PaginationMeta
from app.users.models import User

router = APIRouter(tags=["conversations"])


# ── POST /conversations ────────────────────────────────────────────────────────

@router.post("/conversations", response_model=ApiResponse, status_code=201)
async def create_conversation_endpoint(
    body: ConversationCreateRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    conversation = await create_conversation(body, current_user.id, db)
    data = ConversationResponse.model_validate(conversation)
    return ApiResponse(
        success=True,
        data=data.model_dump(mode="json"),
        message="Conversation created successfully",
    )


# ── GET /conversations ─────────────────────────────────────────────────────────

@router.get("/conversations", response_model=PaginatedResponse)
async def list_conversations_endpoint(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> PaginatedResponse:
    conversations, total = await list_conversations(
        current_user.id, page, page_size, db
    )
    items = [
        ConversationResponse.model_validate(c).model_dump(mode="json")
        for c in conversations
    ]
    return PaginatedResponse(
        success=True,
        data=items,
        message="Conversations retrieved successfully",
        pagination=PaginationMeta(
            total=total,
            page=page,
            page_size=page_size,
            total_pages=max(1, math.ceil(total / page_size)),
        ),
    )


# ── GET /conversations/{conversation_id} ──────────────────────────────────────

@router.get("/conversations/{conversation_id}", response_model=ApiResponse)
async def get_conversation_endpoint(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    conversation = await get_conversation_or_404(conversation_id, current_user.id, db)
    data = ConversationResponse.model_validate(conversation)
    return ApiResponse(
        success=True,
        data=data.model_dump(mode="json"),
        message="Conversation retrieved successfully",
    )


# ── DELETE /conversations/{conversation_id} ────────────────────────────────────

@router.delete("/conversations/{conversation_id}", response_model=ApiResponse)
async def delete_conversation_endpoint(
    conversation_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    conversation = await get_conversation_or_404(conversation_id, current_user.id, db)
    await delete_conversation(conversation, db)
    return ApiResponse(
        success=True,
        data=None,
        message="Conversation deleted successfully",
    )


# ── GET /conversations/{conversation_id}/messages ─────────────────────────────

@router.get(
    "/conversations/{conversation_id}/messages",
    response_model=ApiResponse,
)
async def list_messages_endpoint(
    conversation_id: uuid.UUID,
    cursor: uuid.UUID | None = Query(default=None),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
) -> ApiResponse:
    conversation = await get_conversation_or_404(conversation_id, current_user.id, db)
    msgs, next_cursor = await get_messages(conversation, cursor, page_size, db)
    message_responses = [MessageResponse.from_orm_coerce(m) for m in msgs]
    page_data = MessagePageResponse(
        messages=message_responses,
        next_cursor=next_cursor,
    )
    return ApiResponse(
        success=True,
        data=page_data.model_dump(mode="json"),
        message="Messages retrieved successfully",
    )
