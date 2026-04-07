"""
Schemas for the retrieval (semantic search) component.

SearchRequest  — inbound request body for POST /search.
SearchResult   — a single ranked result chunk with source metadata.
SearchResponse — the data payload returned inside ApiResponse.
"""
import uuid

from pydantic import BaseModel, Field


class SearchRequest(BaseModel):
    query: str = Field(..., min_length=1, max_length=2000, description="Natural language search query")
    domain_id: uuid.UUID | None = Field(
        default=None,
        description="Restrict search to this domain. Must be owned by the caller.",
    )
    top_k: int = Field(default=10, ge=1, le=50, description="Maximum number of results to return")


class SearchResult(BaseModel):
    chunk_id: uuid.UUID
    document_id: uuid.UUID
    domain_id: uuid.UUID
    document_title: str
    chunk_index: int
    text: str
    score: float = Field(..., description="Cosine similarity score in [0, 1]")


class SearchResponse(BaseModel):
    results: list[SearchResult]
    total: int
