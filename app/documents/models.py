import uuid
from datetime import datetime, timezone

from pgvector.sqlalchemy import Vector
from sqlalchemy import DateTime, ForeignKey, Index, Integer, String, Text
from sqlalchemy.dialects.postgresql import UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base
from app.shared.enums import DocumentStatus


class Document(Base):
    __tablename__ = "documents"
    __table_args__ = (
        # Composite index for the most common list query pattern.
        Index("ix_documents_domain_id_deleted_at", "domain_id", "deleted_at"),
        Index("ix_documents_owner_id", "owner_id"),
        Index("ix_documents_status", "status"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    # Denormalized from domain.owner_id — avoids join on ownership checks.
    owner_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    domain_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("knowledge_domains.id", ondelete="CASCADE"),
        nullable=False,
    )
    title: Mapped[str] = mapped_column(String(500), nullable=False)
    # Original filename is user-facing metadata only; never used in storage paths.
    original_filename: Mapped[str] = mapped_column(String(500), nullable=False)
    # UUID-keyed path returned by the storage backend.
    file_key: Mapped[str] = mapped_column(String(1000), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    mime_type: Mapped[str] = mapped_column(String(127), nullable=False)
    # Stored as VARCHAR — avoids DB-level enum migration overhead.
    status: Mapped[str] = mapped_column(
        String(32), nullable=False, default=DocumentStatus.pending.value
    )
    # Populated by the processing pipeline after indexing.
    chunk_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    # Set on failure to record the error that caused the pipeline to fail.
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True, default=None)
    # Soft-delete sentinel. NULL = active. Non-NULL = deleted.
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc),
        nullable=False,
    )


class DocumentChunk(Base):
    __tablename__ = "document_chunks"
    __table_args__ = (
        Index("ix_document_chunks_document_id", "document_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    document_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("documents.id", ondelete="CASCADE"),
        nullable=False,
    )
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    # Populated by the processing pipeline; NULL until embeddings are generated.
    embedding: Mapped[list[float] | None] = mapped_column(
        Vector(1536), nullable=True, default=None
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
