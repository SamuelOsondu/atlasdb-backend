import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.shared.enums import DocumentStatus


class DocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    domain_id: uuid.UUID
    title: str
    original_filename: str
    file_key: str
    file_size: int
    mime_type: str
    status: DocumentStatus
    chunk_count: int = Field(default=0, description="Number of processed chunks (0 until indexed)")
    error_message: str | None = None
    deleted_at: datetime | None
    created_at: datetime
    updated_at: datetime


class DocumentListResponse(BaseModel):
    """Slimmed-down view used in list endpoints — excludes file_key."""
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    domain_id: uuid.UUID
    title: str
    original_filename: str
    file_size: int
    mime_type: str
    status: DocumentStatus
    chunk_count: int = Field(default=0)
    created_at: datetime
    updated_at: datetime
