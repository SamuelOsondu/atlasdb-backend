import uuid

import pytest
from httpx import AsyncClient

from app.domains.models import KnowledgeDomain
from app.users.models import User


# ── POST /domains ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_domain_returns_201(
    client: AsyncClient, user_with_token: tuple[User, str]
):
    _, token = user_with_token
    response = await client.post(
        "/api/v1/domains",
        json={"name": "Engineering Docs", "description": "All eng knowledge"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["name"] == "Engineering Docs"
    assert body["data"]["description"] == "All eng knowledge"
    assert "id" in body["data"]
    assert "owner_id" in body["data"]


@pytest.mark.asyncio
async def test_create_domain_requires_auth(client: AsyncClient):
    response = await client.post("/api/v1/domains", json={"name": "Test"})
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_create_domain_empty_name_returns_422(
    client: AsyncClient, user_with_token: tuple[User, str]
):
    _, token = user_with_token
    response = await client.post(
        "/api/v1/domains",
        json={"name": "   "},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_domain_missing_name_returns_422(
    client: AsyncClient, user_with_token: tuple[User, str]
):
    _, token = user_with_token
    response = await client.post(
        "/api/v1/domains",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_create_domain_duplicate_name_returns_409(
    client: AsyncClient, user_with_token: tuple[User, str]
):
    _, token = user_with_token
    payload = {"name": "Duplicate Domain"}
    await client.post("/api/v1/domains", json=payload, headers={"Authorization": f"Bearer {token}"})
    response = await client.post(
        "/api/v1/domains", json=payload, headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 409


# ── GET /domains ───────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_domains_returns_paginated(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
):
    _, token = user_with_token
    response = await client.get(
        "/api/v1/domains", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert "pagination" in body
    assert body["pagination"]["total"] >= 1


@pytest.mark.asyncio
async def test_list_domains_does_not_return_other_users_domains(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    other_user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
):
    _, other_token = other_user_with_token
    response = await client.get(
        "/api/v1/domains", headers={"Authorization": f"Bearer {other_token}"}
    )
    # The domain fixture belongs to user_with_token; other user should see none of them
    ids = [d["id"] for d in response.json()["data"]]
    assert str(domain.id) not in ids


@pytest.mark.asyncio
async def test_list_domains_empty_for_new_user(
    client: AsyncClient, other_user_with_token: tuple[User, str]
):
    _, token = other_user_with_token
    response = await client.get(
        "/api/v1/domains", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert response.json()["pagination"]["total"] == 0


# ── GET /domains/{id} ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_domain_returns_detail(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
):
    _, token = user_with_token
    response = await client.get(
        f"/api/v1/domains/{domain.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(domain.id)


@pytest.mark.asyncio
async def test_get_domain_returns_404_for_other_users_domain(
    client: AsyncClient,
    other_user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
):
    _, token = other_user_with_token
    response = await client.get(
        f"/api/v1/domains/{domain.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_domain_returns_404_for_random_id(
    client: AsyncClient, user_with_token: tuple[User, str]
):
    _, token = user_with_token
    response = await client.get(
        f"/api/v1/domains/{uuid.uuid4()}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


# ── PATCH /domains/{id} ───────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_domain_name(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
):
    _, token = user_with_token
    response = await client.patch(
        f"/api/v1/domains/{domain.id}",
        json={"name": "Updated Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Updated Name"


@pytest.mark.asyncio
async def test_update_domain_clears_description(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
):
    _, token = user_with_token
    response = await client.patch(
        f"/api/v1/domains/{domain.id}",
        json={"description": None},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["description"] is None


@pytest.mark.asyncio
async def test_update_domain_empty_body_returns_422(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
):
    _, token = user_with_token
    response = await client.patch(
        f"/api/v1/domains/{domain.id}",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_update_domain_forbidden_for_other_user(
    client: AsyncClient,
    other_user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
):
    _, token = other_user_with_token
    response = await client.patch(
        f"/api/v1/domains/{domain.id}",
        json={"name": "Hijack"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


# ── DELETE /domains/{id} ──────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_domain_returns_200(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
):
    _, token = user_with_token
    response = await client.delete(
        f"/api/v1/domains/{domain.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_delete_domain_removes_it(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
):
    _, token = user_with_token
    await client.delete(
        f"/api/v1/domains/{domain.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    response = await client.get(
        f"/api/v1/domains/{domain.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_domain_forbidden_for_other_user(
    client: AsyncClient,
    other_user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
):
    _, token = other_user_with_token
    response = await client.delete(
        f"/api/v1/domains/{domain.id}",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


# ── response shape ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_response_shape_on_create(
    client: AsyncClient, user_with_token: tuple[User, str]
):
    _, token = user_with_token
    response = await client.post(
        "/api/v1/domains",
        json={"name": "Shape Test"},
        headers={"Authorization": f"Bearer {token}"},
    )
    body = response.json()
    assert "success" in body
    assert "data" in body
    assert "message" in body
