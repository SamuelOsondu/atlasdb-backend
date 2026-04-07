"""
Pydantic schemas for the conversations component.

ConversationCreateRequest  — body for POST /conversations
ConversationResponse       — single conversation (create, get, list items)
MessageResponse            — single message in history
MessagePageResponse        — cursor-paginated message list payload
"""
import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class ConversationCreateRequest(BaseModel):
    # User-provided title.  If omitted, title is auto-generated from the
    # first user message when it is appended by the query engine.
    title: str | None = Field(default=None, max_length=255)
    # Optional domain scope.  NULL = search across all user's indexed documents.
    domain_id: uuid.UUID | None = None


class ConversationResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    user_id: uuid.UUID
    title: str | None
    domain_id: uuid.UUID | None
    created_at: datetime
    updated_at: datetime


class MessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    conversation_id: uuid.UUID
    role: str
    content: str
    # Coerce NULL (user messages have no citations) to an empty list for
    # consistent API consumers.
    citations: list = Field(default_factory=list)
    created_at: datetime

    @classmethod
    def from_orm_coerce(cls, msg) -> "MessageResponse":
        """Build a MessageResponse, replacing NULL citations with []."""
        return cls(
            id=msg.id,
            conversation_id=msg.conversation_id,
            role=msg.role,
            content=msg.content,
            citations=msg.citations if msg.citations is not None else [],
            created_at=msg.created_at,
        )


class MessagePageResponse(BaseModel):
    messages: list[MessageResponse]
    # ID of the last message in the current page; pass as `cursor` in the
    # next request to retrieve subsequent messages.  NULL when no more pages.
    next_cursor: uuid.UUID | None
