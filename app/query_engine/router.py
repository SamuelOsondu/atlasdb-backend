"""Query engine router.

Endpoints:
  POST   /api/v1/conversations/{conversation_id}/query
      Submit a query against a conversation.  Streams the response as SSE.
      Rate limited to 10 requests per minute per authenticated user.
      The first SSE event contains the ``request_id`` for use with the cancel
      endpoint.

  DELETE /api/v1/conversations/{conversation_id}/query/{request_id}
      Cancel an in-flight streaming query.  Sets a ``cancel:{request_id}``
      key in Redis (TTL 300 s).  The generator polls this key between tokens
      and terminates cleanly when detected.
"""
import uuid

from fastapi import APIRouter, Depends, Request
from fastapi.responses import StreamingResponse
from slowapi.util import get_remote_address

from app.conversations.service import get_conversation_or_404
from app.core.dependencies import get_current_user, get_db
from app.core.rate_limit import limiter
from app.core.redis_client import get_redis
from app.core.security import decode_access_token
from app.query_engine.schemas import QueryRequest
from app.query_engine.service import handle_query
from app.shared.schemas import ApiResponse

router = APIRouter(tags=["query_engine"])


# ── Per-user rate-limit key ───────────────────────────────────────────────────

def _get_user_key(request: Request) -> str:
    """Extract a stable rate-limit key from the Bearer JWT (user ID).

    Falls back to remote IP if the token is absent or invalid so that
    unauthenticated callers are still limited (they will get 401 anyway via
    ``get_current_user`` before any LLM work begins).
    """
    auth = request.headers.get("Authorization", "")
    if auth.startswith("Bearer "):
        user_id = decode_access_token(auth[7:])
        if user_id:
            return f"user:{user_id}"
    return get_remote_address(request)


# ── Endpoints ─────────────────────────────────────────────────────────────────

@router.post("/conversations/{conversation_id}/query")
@limiter.limit("10/minute", key_func=_get_user_key)
async def query_conversation(
    request: Request,
    conversation_id: uuid.UUID,
    body: QueryRequest,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
) -> StreamingResponse:
    """Submit a natural-language query against a conversation.

    Verifies conversation ownership, then streams the RAG response as
    Server-Sent Events.  Each event is a JSON object on a ``data:`` line
    followed by a blank line.

    Rate limited: 10 requests per minute per user.

    Returns:
        ``StreamingResponse`` with ``media_type="text/event-stream"``.
        HTTP 404 if the conversation does not belong to the caller.
        HTTP 429 if the rate limit is exceeded.
    """
    conversation = await get_conversation_or_404(
        conversation_id, current_user.id, db
    )
    request_id = uuid.uuid4()
    redis_client = await get_redis()

    return StreamingResponse(
        handle_query(
            conversation=conversation,
            query=body.query,
            request_id=request_id,
            user_id=current_user.id,
            db=db,
            redis_client=redis_client,
        ),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@router.delete(
    "/conversations/{conversation_id}/query/{request_id}",
    response_model=ApiResponse,
)
async def cancel_query(
    conversation_id: uuid.UUID,
    request_id: uuid.UUID,
    current_user=Depends(get_current_user),
    db=Depends(get_db),
) -> ApiResponse:
    """Cancel an in-flight streaming query.

    Ownership of the conversation is verified before the cancellation flag is
    set, so users cannot cancel other users' queries even if they know a valid
    ``request_id``.

    The cancellation is propagated asynchronously: the streaming generator
    polls Redis between tokens and terminates when it detects the flag.  The
    TTL (300 s) ensures the key is cleaned up automatically even if the stream
    has already finished.

    Returns:
        200 with ``{"success": true}`` even if the query has already completed
        — this is intentional (idempotent cancel).
        HTTP 404 if the conversation does not belong to the caller.
    """
    await get_conversation_or_404(conversation_id, current_user.id, db)
    redis_client = await get_redis()
    await redis_client.setex(f"cancel:{request_id}", 300, "1")
    return ApiResponse(
        success=True,
        data=None,
        message="Query cancellation requested",
    )
