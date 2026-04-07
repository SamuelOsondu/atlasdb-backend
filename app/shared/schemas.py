import uuid
from typing import Any

from pydantic import BaseModel


class CitationSchema(BaseModel):
    """A reference to a source document chunk, attached to an assistant message."""

    doc_id: uuid.UUID
    doc_title: str
    chunk_index: int
    excerpt: str


class ApiResponse(BaseModel):
    success: bool
    data: Any = None
    message: str


class PaginationMeta(BaseModel):
    total: int
    page: int
    page_size: int
    total_pages: int


class PaginatedResponse(BaseModel):
    success: bool
    data: Any
    message: str
    pagination: PaginationMeta
