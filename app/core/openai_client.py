from openai import AsyncOpenAI
from openai import OpenAI as _SyncOpenAI

from app.core.config import settings

_client: AsyncOpenAI | None = None
_sync_client: _SyncOpenAI | None = None


def get_openai_client() -> AsyncOpenAI:
    global _client
    if _client is None:
        _client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _client


def get_sync_openai_client() -> _SyncOpenAI:
    global _sync_client
    if _sync_client is None:
        _sync_client = _SyncOpenAI(api_key=settings.OPENAI_API_KEY)
    return _sync_client


async def async_embed_text(text: str) -> list[float]:
    """Asynchronously embed a single query string via the OpenAI embeddings API."""
    client = get_openai_client()
    response = await client.embeddings.create(
        model=settings.EMBEDDING_MODEL,
        input=[text],
    )
    return response.data[0].embedding


async def stream_chat_completion(messages: list[dict]):
    """Async generator that streams chat completion tokens from OpenAI.

    Yields individual text tokens as they arrive from the API.

    Args:
        messages: List of message dicts with 'role' and 'content' keys.

    Raises:
        Exception: Propagates any OpenAI API errors to the caller.
    """
    client = get_openai_client()
    stream = await client.chat.completions.create(
        model=settings.LLM_MODEL,
        messages=messages,
        stream=True,
    )
    async for chunk in stream:
        delta = chunk.choices[0].delta
        if delta.content:
            yield delta.content


def embed_texts(texts: list[str]) -> list[list[float]]:
    """Synchronously embed a list of texts in batches using the OpenAI embeddings API."""
    client = get_sync_openai_client()
    batch_size = settings.EMBEDDING_BATCH_SIZE
    results: list[list[float]] = []
    for i in range(0, len(texts), batch_size):
        batch = texts[i : i + batch_size]
        response = client.embeddings.create(model=settings.EMBEDDING_MODEL, input=batch)
        results.extend([item.embedding for item in response.data])
    return results
