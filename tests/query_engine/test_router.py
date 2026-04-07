"""
Router-layer (HTTP integration) tests for the query engine.

External calls (retrieval/embedding and LLM streaming) are monkeypatched so
these tests run without network access and finish quickly.
"""
import json
import uuid

import pytest
from httpx import AsyncClient

from app.conversations.models import Conversation
from app.users.models import User
from tests.query_engine.conftest import FakeRedis, SAMPLE_CHUNKS


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_mock_search(chunks):
    async def _mock(**kwargs):
        return chunks
    return _mock


def _make_mock_stream(tokens: list[str]):
    async def _mock(messages):
        for t in tokens:
            yield t
    return _mock


def _parse_sse(content: bytes) -> list[dict]:
    """Parse raw SSE body into a list of JSON event dicts."""
    events = []
    for line in content.decode().split("\n"):
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


# ── POST /conversations/{id}/query ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_query_requires_authentication(
    client: AsyncClient,
    conversation: Conversation,
):
    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/query",
        json={"query": "What is Paris?"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_query_other_users_conversation_returns_404(
    client: AsyncClient,
    other_user_with_token: tuple[User, str],
    conversation: Conversation,
    monkeypatch,
):
    """Users cannot query a conversation that belongs to someone else."""
    _, token = other_user_with_token
    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/query",
        headers=_auth(token),
        json={"query": "What is Paris?"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_query_nonexistent_conversation_returns_404(
    client: AsyncClient,
    user_with_token: tuple[User, str],
):
    _, token = user_with_token
    response = await client.post(
        f"/api/v1/conversations/{uuid.uuid4()}/query",
        headers=_auth(token),
        json={"query": "Hello?"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_query_returns_event_stream_content_type(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    conversation: Conversation,
    monkeypatch,
):
    monkeypatch.setattr("app.query_engine.service.search", _make_mock_search(SAMPLE_CHUNKS))
    monkeypatch.setattr(
        "app.query_engine.service.stream_chat_completion",
        _make_mock_stream(["Hi"]),
    )
    monkeypatch.setattr("app.query_engine.router.get_redis", lambda: _async_return(FakeRedis()))

    _, token = user_with_token
    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/query",
        headers=_auth(token),
        json={"query": "Test query"},
    )
    assert response.status_code == 200
    assert "text/event-stream" in response.headers["content-type"]


@pytest.mark.asyncio
async def test_query_first_event_contains_request_id(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    conversation: Conversation,
    monkeypatch,
):
    monkeypatch.setattr("app.query_engine.service.search", _make_mock_search(SAMPLE_CHUNKS))
    monkeypatch.setattr(
        "app.query_engine.service.stream_chat_completion",
        _make_mock_stream(["Hello"]),
    )
    monkeypatch.setattr("app.query_engine.router.get_redis", lambda: _async_return(FakeRedis()))

    _, token = user_with_token
    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/query",
        headers=_auth(token),
        json={"query": "What is Paris?"},
    )
    events = _parse_sse(response.content)
    assert "request_id" in events[0]
    # Must be a valid UUID string.
    uuid.UUID(events[0]["request_id"])


@pytest.mark.asyncio
async def test_query_sse_contains_token_events(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    conversation: Conversation,
    monkeypatch,
):
    monkeypatch.setattr("app.query_engine.service.search", _make_mock_search(SAMPLE_CHUNKS))
    monkeypatch.setattr(
        "app.query_engine.service.stream_chat_completion",
        _make_mock_stream(["Paris", " rocks"]),
    )
    monkeypatch.setattr("app.query_engine.router.get_redis", lambda: _async_return(FakeRedis()))

    _, token = user_with_token
    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/query",
        headers=_auth(token),
        json={"query": "Tell me about Paris."},
    )
    events = _parse_sse(response.content)
    token_events = [e for e in events if "token" in e]
    assert len(token_events) == 2


@pytest.mark.asyncio
async def test_query_sse_final_event_is_done(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    conversation: Conversation,
    monkeypatch,
):
    monkeypatch.setattr("app.query_engine.service.search", _make_mock_search(SAMPLE_CHUNKS))
    monkeypatch.setattr(
        "app.query_engine.service.stream_chat_completion",
        _make_mock_stream(["Answer."]),
    )
    monkeypatch.setattr("app.query_engine.router.get_redis", lambda: _async_return(FakeRedis()))

    _, token = user_with_token
    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/query",
        headers=_auth(token),
        json={"query": "Query?"},
    )
    events = _parse_sse(response.content)
    assert events[-1].get("done") is True
    assert "citations" in events[-1]


@pytest.mark.asyncio
async def test_query_empty_query_returns_422(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    conversation: Conversation,
):
    _, token = user_with_token
    response = await client.post(
        f"/api/v1/conversations/{conversation.id}/query",
        headers=_auth(token),
        json={"query": ""},
    )
    assert response.status_code == 422


# ── DELETE /conversations/{id}/query/{request_id} ─────────────────────────────

@pytest.mark.asyncio
async def test_cancel_query_returns_200(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    conversation: Conversation,
    monkeypatch,
):
    monkeypatch.setattr("app.query_engine.router.get_redis", lambda: _async_return(FakeRedis()))

    _, token = user_with_token
    request_id = uuid.uuid4()
    response = await client.delete(
        f"/api/v1/conversations/{conversation.id}/query/{request_id}",
        headers=_auth(token),
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_cancel_query_requires_authentication(
    client: AsyncClient,
    conversation: Conversation,
):
    response = await client.delete(
        f"/api/v1/conversations/{conversation.id}/query/{uuid.uuid4()}"
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_cancel_query_other_users_conversation_returns_404(
    client: AsyncClient,
    other_user_with_token: tuple[User, str],
    conversation: Conversation,
    monkeypatch,
):
    """Cannot cancel a query in a conversation belonging to another user."""
    _, token = other_user_with_token
    response = await client.delete(
        f"/api/v1/conversations/{conversation.id}/query/{uuid.uuid4()}",
        headers=_auth(token),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_cancel_query_is_idempotent(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    conversation: Conversation,
    monkeypatch,
):
    """Cancelling the same request_id twice must return 200 both times."""
    monkeypatch.setattr("app.query_engine.router.get_redis", lambda: _async_return(FakeRedis()))

    _, token = user_with_token
    request_id = uuid.uuid4()
    url = f"/api/v1/conversations/{conversation.id}/query/{request_id}"

    r1 = await client.delete(url, headers=_auth(token))
    r2 = await client.delete(url, headers=_auth(token))
    assert r1.status_code == 200
    assert r2.status_code == 200


# ── Helpers ───────────────────────────────────────────────────────────────────

async def _async_return(value):
    """Awaitable that returns *value* immediately."""
    return value
