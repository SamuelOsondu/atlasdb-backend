"""
Retrieval service — semantic search over indexed document chunks.

Entry point: search(query, user_id, domain_id, top_k, db, threshold)

Design notes:
  - Ownership enforced at the SQL level via JOIN to knowledge_domains.owner_id.
    No application-level post-filter is used; un-authorised chunks never reach Python.
  - Soft-deleted documents are excluded via d.deleted_at IS NULL in the same query.
  - Chunks without embeddings (dc.embedding IS NULL) are skipped — they are not yet indexed.
  - The similarity threshold is applied inside the SQL WHERE clause so the DB discards
    low-relevance rows before they are transferred to the application layer.
  - The `threshold` parameter defaults to None, falling back to settings.MIN_SIMILARITY_SCORE.
    Query engine callers may pass a different threshold (e.g. settings.MAX_CHUNKS_PER_QUERY context).
"""
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.core.exceptions import ServiceUnavailableError
from app.core.openai_client import async_embed_text
from app.domains.service import get_domain_or_404
from app.retrieval.schemas import SearchResult


async def search(
    query: str,
    user_id: uuid.UUID,
    domain_id: uuid.UUID | None,
    top_k: int,
    db: AsyncSession,
    threshold: float | None = None,
) -> list[SearchResult]:
    """
    Perform a semantic similarity search and return ranked results.

    Args:
        query:     Natural language search string.
        user_id:   Caller's user ID — used to enforce ownership.
        domain_id: If provided, restrict search to this domain (ownership verified first).
        top_k:     Maximum number of results to return.
        db:        Async SQLAlchemy session.
        threshold: Minimum cosine similarity score.  Defaults to settings.MIN_SIMILARITY_SCORE.

    Returns:
        List of SearchResult ordered by descending similarity score.

    Raises:
        NotFoundError:          domain_id is given but not owned by user_id.
        ServiceUnavailableError: OpenAI embedding call failed.
    """
    if threshold is None:
        threshold = settings.MIN_SIMILARITY_SCORE

    # ── 1. Domain ownership guard ─────────────────────────────────────────────
    if domain_id is not None:
        # Raises NotFoundError (→ 404) if domain doesn't exist or isn't owned by user.
        await get_domain_or_404(domain_id, user_id, db)

    # ── 2. Embed the query ────────────────────────────────────────────────────
    try:
        query_embedding = await async_embed_text(query)
    except Exception as exc:
        raise ServiceUnavailableError(
            f"Failed to generate query embedding: {exc}"
        ) from exc

    # Format as pgvector literal string: '[0.1,0.2,...]'
    embedding_str = "[" + ",".join(str(v) for v in query_embedding) + "]"

    # ── 3. Vector similarity search ───────────────────────────────────────────
    # The `<=>` operator is pgvector's cosine distance; 1 - distance = similarity.
    # All ownership + soft-delete filters are applied inline so no unauthed rows
    # are ever transferred to the Python layer.
    sql = """
        SELECT
            dc.id,
            dc.chunk_index,
            dc.text,
            d.id          AS document_id,
            d.title       AS document_title,
            d.domain_id,
            1 - (dc.embedding <=> (:query_embedding)::vector) AS score
        FROM document_chunks dc
        JOIN documents d  ON dc.document_id = d.id
        JOIN knowledge_domains kd ON d.domain_id = kd.id
        WHERE kd.owner_id = :user_id
          AND d.deleted_at IS NULL
          AND dc.embedding IS NOT NULL
          AND 1 - (dc.embedding <=> (:query_embedding)::vector) >= :threshold
    """

    params: dict = {
        "query_embedding": embedding_str,
        "user_id": user_id,
        "threshold": threshold,
        "top_k": top_k,
    }

    # Conditionally add domain scope — avoids passing NULL UUID to asyncpg which
    # cannot infer the parameter type without an explicit cast.
    if domain_id is not None:
        sql += " AND kd.id = :domain_id"
        params["domain_id"] = domain_id

    sql += " ORDER BY dc.embedding <=> (:query_embedding)::vector LIMIT :top_k"

    result = await db.execute(text(sql), params)
    rows = result.fetchall()

    return [
        SearchResult(
            chunk_id=row.id,
            document_id=row.document_id,
            domain_id=row.domain_id,
            document_title=row.document_title,
            chunk_index=row.chunk_index,
            text=row.text,
            score=float(row.score),
        )
        for row in rows
    ]
