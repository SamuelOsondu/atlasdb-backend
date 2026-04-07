"""
Router-layer (HTTP integration) tests for the retrieval component.

async_embed_text is patched via monkeypatch so no real OpenAI calls occur.
All tests use the real test DB — chunks are inserted via the conftest fixtures.
"""
import uuid

import pytest
from httpx import AsyncClient

from app.domains.models import KnowledgeDomain
from app.users.models import User
from tests.retrieval.conftest import MATCH_EMBEDDING, QUERY_EMBEDDING


# ── helpers ────────────────────────────────────────────────────────────────────

def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _mock_embed(monkeypatch, embedding=None):
    vec = embedding if embedding is not None else QUERY_EMBEDDING

    async def _fake(text: str) -> list[float]:
        return vec

    monkeypatch.setattr("app.retrieval.service.async_embed_text", _fake)


# ── POST /api/v1/search ────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_returns_200_with_results(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    document_with_chunks,
    monkeypatch,
):
    """Happy path: authenticated user gets results with correct shape."""
    _mock_embed(monkeypatch)
    _, token = user_with_token

    response = await client.post(
        "/api/v1/search",
        headers=_auth(token),
        json={"query": "find relevant content"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "results" in body["data"]
    assert "total" in body["data"]
    assert body["data"]["total"] >= 1
    # Each result must have the required fields
    r = body["data"]["results"][0]
    assert "chunk_id" in r
    assert "document_id" in r
    assert "domain_id" in r
    assert "document_title" in r
    assert "chunk_index" in r
    assert "text" in r
    assert "score" in r
    assert 0.0 <= r["score"] <= 1.0


@pytest.mark.asyncio
async def test_search_returns_empty_list_when_no_matches(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    monkeypatch,
):
    """Empty result set must return 200 with an empty results list, not an error."""
    _mock_embed(monkeypatch)
    _, token = user_with_token

    response = await client.post(
        "/api/v1/search",
        headers=_auth(token),
        json={"query": "no matching documents at all"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["results"] == []
    assert body["data"]["total"] == 0


@pytest.mark.asyncio
async def test_search_with_domain_scoping(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    document_with_chunks,
    monkeypatch,
):
    """domain_id parameter is accepted and scopes results correctly."""
    _mock_embed(monkeypatch)
    _, token = user_with_token

    response = await client.post(
        "/api/v1/search",
        headers=_auth(token),
        json={"query": "test", "domain_id": str(domain.id)},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    # All returned results must belong to the requested domain
    for r in body["data"]["results"]:
        assert r["domain_id"] == str(domain.id)


@pytest.mark.asyncio
async def test_search_with_top_k(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    document_with_chunks,
    monkeypatch,
):
    """top_k=1 must cap the result count at 1."""
    _mock_embed(monkeypatch)
    _, token = user_with_token

    response = await client.post(
        "/api/v1/search",
        headers=_auth(token),
        json={"query": "test", "top_k": 1},
    )

    assert response.status_code == 200
    assert len(response.json()["data"]["results"]) <= 1


# ── auth guards ────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_unauthenticated_returns_401(client: AsyncClient, monkeypatch):
    """Request without Bearer token must be rejected with 401."""
    _mock_embed(monkeypatch)

    response = await client.post(
        "/api/v1/search",
        json={"query": "test"},
    )

    assert response.status_code == 401


@pytest.mark.asyncio
async def test_search_invalid_token_returns_401(client: AsyncClient, monkeypatch):
    """Invalid token must be rejected with 401."""
    _mock_embed(monkeypatch)

    response = await client.post(
        "/api/v1/search",
        headers={"Authorization": "Bearer not-a-real-token"},
        json={"query": "test"},
    )

    assert response.status_code == 401


# ── validation ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_empty_query_returns_422(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    monkeypatch,
):
    """Empty string query must fail Pydantic validation (min_length=1)."""
    _mock_embed(monkeypatch)
    _, token = user_with_token

    response = await client.post(
        "/api/v1/search",
        headers=_auth(token),
        json={"query": ""},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_top_k_out_of_range_returns_422(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    monkeypatch,
):
    """top_k=0 must fail validation (ge=1)."""
    _mock_embed(monkeypatch)
    _, token = user_with_token

    response = await client.post(
        "/api/v1/search",
        headers=_auth(token),
        json={"query": "test", "top_k": 0},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_search_top_k_too_large_returns_422(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    monkeypatch,
):
    """top_k > 50 must fail validation (le=50)."""
    _mock_embed(monkeypatch)
    _, token = user_with_token

    response = await client.post(
        "/api/v1/search",
        headers=_auth(token),
        json={"query": "test", "top_k": 51},
    )

    assert response.status_code == 422


# ── ownership / domain scoping errors ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_other_users_domain_returns_404(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    other_domain: KnowledgeDomain,
    monkeypatch,
):
    """Scoping to another user's domain must return 404 (not 403 — prevents enumeration)."""
    _mock_embed(monkeypatch)
    _, token = user_with_token

    response = await client.post(
        "/api/v1/search",
        headers=_auth(token),
        json={"query": "test", "domain_id": str(other_domain.id)},
    )

    assert response.status_code == 404


@pytest.mark.asyncio
async def test_search_nonexistent_domain_returns_404(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    monkeypatch,
):
    """Scoping to a nonexistent domain UUID must return 404."""
    _mock_embed(monkeypatch)
    _, token = user_with_token

    response = await client.post(
        "/api/v1/search",
        headers=_auth(token),
        json={"query": "test", "domain_id": str(uuid.uuid4())},
    )

    assert response.status_code == 404


# ── 503 on embedding failure ───────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_search_embedding_failure_returns_503(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    monkeypatch,
):
    """OpenAI failure during embedding must return 503 Service Unavailable."""
    async def _fail(text: str):
        raise RuntimeError("OpenAI timeout")

    monkeypatch.setattr("app.retrieval.service.async_embed_text", _fail)
    _, token = user_with_token

    response = await client.post(
        "/api/v1/search",
        headers=_auth(token),
        json={"query": "fail this"},
    )

    assert response.status_code == 503
    body = response.json()
    assert body["success"] is False
