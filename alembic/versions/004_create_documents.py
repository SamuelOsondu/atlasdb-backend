"""Create documents and document_chunks tables

Revision ID: d4e5f6a1b2c3
Revises: c3d4e5f6a1b2
Create Date: 2026-04-07

"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "d4e5f6a1b2c3"
down_revision: Union[str, None] = "c3d4e5f6a1b2"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── documents ────────────────────────────────────────────────────────────
    op.create_table(
        "documents",
        sa.Column("id", UUID(as_uuid=True), primary_key=True),
        sa.Column(
            "owner_id",
            UUID(as_uuid=True),
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "domain_id",
            UUID(as_uuid=True),
            sa.ForeignKey("knowledge_domains.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("title", sa.String(500), nullable=False),
        sa.Column("original_filename", sa.String(500), nullable=False),
        sa.Column("file_key", sa.String(1000), nullable=False),
        sa.Column("file_size", sa.Integer, nullable=False),
        sa.Column("mime_type", sa.String(127), nullable=False),
        sa.Column("status", sa.String(32), nullable=False, server_default="pending"),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_documents_domain_id_deleted_at",
        "documents",
        ["domain_id", "deleted_at"],
    )
    op.create_index("ix_documents_owner_id", "documents", ["owner_id"])
    op.create_index("ix_documents_status", "documents", ["status"])

    # ── document_chunks ───────────────────────────────────────────────────────
    # The embedding column uses the pgvector vector type which cannot be expressed
    # via SQLAlchemy core types directly in op.create_table, so we use raw DDL.
    op.execute(
        """
        CREATE TABLE document_chunks (
            id          UUID        PRIMARY KEY,
            document_id UUID        NOT NULL REFERENCES documents(id) ON DELETE CASCADE,
            chunk_index INTEGER     NOT NULL,
            text        TEXT        NOT NULL,
            embedding   vector(1536),
            created_at  TIMESTAMPTZ NOT NULL
        )
        """
    )
    op.create_index(
        "ix_document_chunks_document_id", "document_chunks", ["document_id"]
    )
    # HNSW index for fast approximate nearest-neighbour search.
    # m=16 (connections per layer), ef_construction=64 (build-time search candidates).
    op.execute(
        """
        CREATE INDEX ix_document_chunks_embedding_hnsw
        ON document_chunks
        USING hnsw (embedding vector_cosine_ops)
        WITH (m = 16, ef_construction = 64)
        """
    )


def downgrade() -> None:
    op.drop_table("document_chunks")
    op.drop_table("documents")
