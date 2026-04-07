"""Async Redis client singleton for AtlasDB.

Used by the query engine to manage in-flight query cancellation flags
via short-lived keys (``cancel:{request_id}``).

Usage::

    from app.core.redis_client import get_redis
    redis = await get_redis()
    await redis.setex("cancel:some-uuid", 300, "1")
"""
import redis.asyncio as aioredis

from app.core.config import settings

_client: aioredis.Redis | None = None


async def get_redis() -> aioredis.Redis:
    """Return (or lazily create) the shared async Redis client.

    The client is created once per process and reused across requests.
    Connection pooling is handled internally by redis-py.
    """
    global _client
    if _client is None:
        _client = aioredis.from_url(
            settings.REDIS_URL,
            encoding="utf-8",
            decode_responses=True,
        )
    return _client
