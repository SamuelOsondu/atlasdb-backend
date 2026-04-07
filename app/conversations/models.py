"""
SQLAlchemy models for the conversations component.

Conversation  — a stateful session grouping a user's queries and assistant responses.
Message       — a single turn (user or assistant) within a conversation.

Design notes:
  - domain_id uses ON DELETE SET NULL so conversations survive domain deletion.
    A NULL domain_id means the conversation is cross-domain (searches all user docs).
  - Conversation hard-delete cascades to Messages at the DB level (FK CASCADE).
  - citations stored as JSONB — a list of CitationSchema-shaped dicts written by
    the query engine. NULL for user messages; populated for assistant messages.
  - role stored as VARCHAR(16) matching MessageRole enum values ("user"/"assistant").
    Avoids DB enum migration churn.
"""
import uuid
from datetime import datetime, timezone

from sqlalchemy import DateTime, ForeignKey, Index, String, Text
from sqlalchemy.dialects.postgresql import JSONB, UUID as PG_UUID
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class Conversation(Base):
    __tablename__ = "conversations"
    __table_args__ = (
        Index("ix_conversations_user_id", "user_id"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    user_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    # Nullable: NULL means cross-domain (search all user's indexed docs).
    # ON DELETE SET NULL preserves the conversation if the domain is deleted.
    domain_id: Mapped[uuid.UUID | None] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("knowledge_domains.id", ondelete="SET NULL"),
        nullable=True,
        default=None,
    )
    # Auto-generated from first user message (first 60 chars) if not provided.
    title: Mapped[str | None] = mapped_column(String(255), nullable=True, default=None)
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


class Message(Base):
    __tablename__ = "messages"
    __table_args__ = (
        # Composite index for efficient cursor-based pagination ordered by creation time.
        Index("ix_messages_conversation_id_created_at", "conversation_id", "created_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    conversation_id: Mapped[uuid.UUID] = mapped_column(
        PG_UUID(as_uuid=True),
        ForeignKey("conversations.id", ondelete="CASCADE"),
        nullable=False,
    )
    # "user" or "assistant" — matches MessageRole enum values.
    role: Mapped[str] = mapped_column(String(16), nullable=False)
    content: Mapped[str] = mapped_column(Text, nullable=False)
    # NULL for user messages; list of CitationSchema dicts for assistant messages.
    citations: Mapped[list | None] = mapped_column(JSONB, nullable=True, default=None)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
