"""
Router-layer (HTTP integration) tests for the conversations component.

No mocks needed — conversations has no external dependencies.
"""
import uuid

import pytest
from httpx import AsyncClient

from app.conversations.models import Conversation
from app.domains.models import KnowledgeDomain
from app.users.models import User


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── POST /api/v1/conversations ────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_conversation_returns_201(
    client: AsyncClient,
    user_with_token: tuple[User, str],
):
    _, token = user_with_token
    response = await client.post(
        "/api/v1/conversations",
        headers=_auth(token),
        json={"title": "Test Conversation"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert data["title"] == "Test Conversation"
    assert data["domain_id"] is None
    assert "id" in data
    assert "created_at" in data


@pytest.mark.asyncio
async def test_create_conversation_no_title(
    client: AsyncClient,
    user_with_token: tuple[User, str],
):
    _, token = user_with_token
    response = await client.post(
        "/api/v1/conversations",
        headers=_auth(token),
        json={},
    )
    assert response.status_code == 201
    assert response.json()["data"]["title"] is None


@pytest.mark.asyncio
async def test_create_conversation_with_domain(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
):
    _, token = user_with_token
    response = await client.post(
        "/api/v1/conversations",
        headers=_auth(token),
        json={"domain_id": str(domain.id)},
    )
    assert response.status_code == 201
    assert response.json()["data"]["domain_id"] == str(domain.id)


@pytest.mark.asyncio
async def test_create_conversation_other_users_domain_returns_404(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    other_domain: KnowledgeDomain,
):
    _, token = user_with_token
    response = await client.post(
        "/api/v1/conversations",
        headers=_auth(token),
        json={"domain_id": str(other_domain.id)},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_create_conversation_unauthenticated_returns_401(
    client: AsyncClient,
):
    response = await client.post("/api/v1/conversations", json={"title": "x"})
    assert response.status_code == 401


# ── GET /api/v1/conversations ─────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_conversations_returns_200(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    conversation: Conversation,
):
    _, token = user_with_token
    response = await client.get("/api/v1/conversations", headers=_auth(token))
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "pagination" in body
    ids = [c["id"] for c in body["data"]]
    assert str(conversation.id) in ids


@pytest.mark.asyncio
async def test_list_conversations_excludes_other_users(
    client: AsyncClient,
    other_user_with_token: tuple[User, str],
    conversation: Conversation,
):
    """other_user must not see the primary user's conversation."""
    _, token = other_user_with_token
    response = await client.get("/api/v1/conversations", headers=_auth(token))
    assert response.status_code == 200
    ids = [c["id"] for c in response.json()["data"]]
    assert str(conversation.id) not in ids


@pytest.mark.asyncio
async def test_list_conversations_pagination_params(
    client: AsyncClient,
    user_with_token: tuple[User, str],
):
    _, token = user_with_token
    response = await client.get(
        "/api/v1/conversations?page=1&page_size=5", headers=_auth(token)
    )
    assert response.status_code == 200
    meta = response.json()["pagination"]
    assert meta["page"] == 1
    assert meta["page_size"] == 5


# ── GET /api/v1/conversations/{id} ───────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_conversation_returns_200(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    conversation: Conversation,
):
    _, token = user_with_token
    response = await client.get(
        f"/api/v1/conversations/{conversation.id}", headers=_auth(token)
    )
    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(conversation.id)


@pytest.mark.asyncio
async def test_get_conversation_other_user_returns_404(
    client: AsyncClient,
    other_user_with_token: tuple[User, str],
    conversation: Conversation,
):
    _, token = other_user_with_token
    response = await client.get(
        f"/api/v1/conversations/{conversation.id}", headers=_auth(token)
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_conversation_nonexistent_returns_404(
    client: AsyncClient,
    user_with_token: tuple[User, str],
):
    _, token = user_with_token
    response = await client.get(
        f"/api/v1/conversations/{uuid.uuid4()}", headers=_auth(token)
    )
    assert response.status_code == 404


# ── DELETE /api/v1/conversations/{id} ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_conversation_returns_200(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    conversation: Conversation,
):
    _, token = user_with_token
    response = await client.delete(
        f"/api/v1/conversations/{conversation.id}", headers=_auth(token)
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_delete_conversation_no_longer_accessible(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    conversation: Conversation,
):
    """After deletion, GET returns 404."""
    _, token = user_with_token
    await client.delete(
        f"/api/v1/conversations/{conversation.id}", headers=_auth(token)
    )
    response = await client.get(
        f"/api/v1/conversations/{conversation.id}", headers=_auth(token)
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_conversation_other_user_returns_404(
    client: AsyncClient,
    other_user_with_token: tuple[User, str],
    conversation: Conversation,
):
    _, token = other_user_with_token
    response = await client.delete(
        f"/api/v1/conversations/{conversation.id}", headers=_auth(token)
    )
    assert response.status_code == 404


# ── GET /api/v1/conversations/{id}/messages ───────────────────────────────────

@pytest.mark.asyncio
async def test_list_messages_returns_200(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    conversation_with_messages: Conversation,
):
    _, token = user_with_token
    response = await client.get(
        f"/api/v1/conversations/{conversation_with_messages.id}/messages",
        headers=_auth(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    data = body["data"]
    assert len(data["messages"]) == 2
    assert data["next_cursor"] is None


@pytest.mark.asyncio
async def test_list_messages_ordering_oldest_first(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    conversation_with_messages: Conversation,
):
    """Messages returned in ascending created_at order (oldest first)."""
    _, token = user_with_token
    response = await client.get(
        f"/api/v1/conversations/{conversation_with_messages.id}/messages",
        headers=_auth(token),
    )
    msgs = response.json()["data"]["messages"]
    assert msgs[0]["role"] == "user"
    assert msgs[1]["role"] == "assistant"


@pytest.mark.asyncio
async def test_list_messages_citations_present(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    conversation_with_messages: Conversation,
):
    """Assistant message carries the citations it was appended with."""
    _, token = user_with_token
    response = await client.get(
        f"/api/v1/conversations/{conversation_with_messages.id}/messages",
        headers=_auth(token),
    )
    msgs = response.json()["data"]["messages"]
    assistant_msg = next(m for m in msgs if m["role"] == "assistant")
    assert len(assistant_msg["citations"]) == 1
    assert assistant_msg["citations"][0]["doc_title"] == "Europe Guide"


@pytest.mark.asyncio
async def test_list_messages_user_message_citations_empty(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    conversation_with_messages: Conversation,
):
    """User messages have no citations — response should be empty list, not null."""
    _, token = user_with_token
    response = await client.get(
        f"/api/v1/conversations/{conversation_with_messages.id}/messages",
        headers=_auth(token),
    )
    msgs = response.json()["data"]["messages"]
    user_msg = next(m for m in msgs if m["role"] == "user")
    assert user_msg["citations"] == []


@pytest.mark.asyncio
async def test_list_messages_cursor_pagination(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    conversation_with_messages: Conversation,
):
    """page_size=1 on a 2-message conversation returns one message and a next_cursor."""
    _, token = user_with_token
    response = await client.get(
        f"/api/v1/conversations/{conversation_with_messages.id}/messages?page_size=1",
        headers=_auth(token),
    )
    data = response.json()["data"]
    assert len(data["messages"]) == 1
    assert data["next_cursor"] is not None

    # Fetch second page
    cursor = data["next_cursor"]
    response2 = await client.get(
        f"/api/v1/conversations/{conversation_with_messages.id}/messages"
        f"?page_size=1&cursor={cursor}",
        headers=_auth(token),
    )
    data2 = response2.json()["data"]
    assert len(data2["messages"]) == 1
    assert data2["next_cursor"] is None
    # Second page's message is different from first page's
    assert data2["messages"][0]["id"] != data["messages"][0]["id"]


@pytest.mark.asyncio
async def test_list_messages_other_user_conversation_returns_404(
    client: AsyncClient,
    other_user_with_token: tuple[User, str],
    conversation_with_messages: Conversation,
):
    _, token = other_user_with_token
    response = await client.get(
        f"/api/v1/conversations/{conversation_with_messages.id}/messages",
        headers=_auth(token),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_messages_unauthenticated_returns_401(
    client: AsyncClient,
    conversation_with_messages: Conversation,
):
    response = await client.get(
        f"/api/v1/conversations/{conversation_with_messages.id}/messages"
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_list_messages_invalid_cursor_returns_404(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    conversation: Conversation,
):
    """Invalid cursor UUID returns 404."""
    _, token = user_with_token
    response = await client.get(
        f"/api/v1/conversations/{conversation.id}/messages"
        f"?cursor={uuid.uuid4()}",
        headers=_auth(token),
    )
    assert response.status_code == 404
