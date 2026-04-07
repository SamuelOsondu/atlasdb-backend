import uuid

import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.users.models import User


# ── /users/me ─────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_me_returns_own_profile(
    client: AsyncClient, regular_user: tuple[User, str]
):
    user, token = regular_user
    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["email"] == user.email
    assert body["data"]["full_name"] == user.full_name


@pytest.mark.asyncio
async def test_get_me_requires_auth(client: AsyncClient):
    response = await client.get("/api/v1/users/me")
    assert response.status_code == 403  # HTTPBearer returns 403 when no credentials


@pytest.mark.asyncio
async def test_get_me_rejects_invalid_token(client: AsyncClient):
    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": "Bearer invalidtoken"}
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_patch_me_updates_full_name(
    client: AsyncClient, regular_user: tuple[User, str]
):
    _, token = regular_user
    response = await client.patch(
        "/api/v1/users/me",
        json={"full_name": "Updated Name"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["full_name"] == "Updated Name"


@pytest.mark.asyncio
async def test_patch_me_clears_full_name(
    client: AsyncClient, regular_user: tuple[User, str]
):
    _, token = regular_user
    response = await client.patch(
        "/api/v1/users/me",
        json={"full_name": None},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["full_name"] is None


@pytest.mark.asyncio
async def test_patch_me_changes_password(
    client: AsyncClient, regular_user: tuple[User, str]
):
    _, token = regular_user
    response = await client.patch(
        "/api/v1/users/me",
        json={"current_password": "password1", "new_password": "newpassword1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_patch_me_wrong_current_password_returns_422(
    client: AsyncClient, regular_user: tuple[User, str]
):
    _, token = regular_user
    response = await client.patch(
        "/api/v1/users/me",
        json={"current_password": "wrongpass", "new_password": "newpassword1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_patch_me_empty_body_returns_422(
    client: AsyncClient, regular_user: tuple[User, str]
):
    _, token = regular_user
    response = await client.patch(
        "/api/v1/users/me",
        json={},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_patch_me_only_new_password_returns_422(
    client: AsyncClient, regular_user: tuple[User, str]
):
    # Providing new_password without current_password must fail at schema validation
    _, token = regular_user
    response = await client.patch(
        "/api/v1/users/me",
        json={"new_password": "newpassword1"},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


# ── /admin/users ──────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_list_users_returns_paginated(
    client: AsyncClient, admin_user: tuple[User, str]
):
    _, token = admin_user
    response = await client.get(
        "/api/v1/admin/users?page=1&page_size=10",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert "pagination" in body
    assert body["pagination"]["page"] == 1
    assert isinstance(body["data"], list)


@pytest.mark.asyncio
async def test_admin_list_users_rejects_non_admin(
    client: AsyncClient, regular_user: tuple[User, str]
):
    _, token = regular_user
    response = await client.get(
        "/api/v1/admin/users", headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_deactivate_user(
    client: AsyncClient,
    admin_user: tuple[User, str],
    second_user: tuple[User, str],
):
    _, admin_token = admin_user
    target_user, _ = second_user

    response = await client.patch(
        f"/api/v1/admin/users/{target_user.id}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["is_active"] is False


@pytest.mark.asyncio
async def test_admin_reactivate_user(
    client: AsyncClient,
    admin_user: tuple[User, str],
    second_user: tuple[User, str],
):
    _, admin_token = admin_user
    target_user, _ = second_user

    # Deactivate first
    await client.patch(
        f"/api/v1/admin/users/{target_user.id}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    # Then reactivate
    response = await client.patch(
        f"/api/v1/admin/users/{target_user.id}/reactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["is_active"] is True


@pytest.mark.asyncio
async def test_admin_cannot_deactivate_self(
    client: AsyncClient, admin_user: tuple[User, str]
):
    admin, token = admin_user
    response = await client.patch(
        f"/api/v1/admin/users/{admin.id}/deactivate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_admin_deactivate_nonexistent_user_returns_404(
    client: AsyncClient, admin_user: tuple[User, str]
):
    _, token = admin_user
    response = await client.patch(
        f"/api/v1/admin/users/{uuid.uuid4()}/deactivate",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_deactivated_user_login_returns_403(
    client: AsyncClient,
    admin_user: tuple[User, str],
    second_user: tuple[User, str],
):
    """Spec: deactivated users cannot authenticate — login returns 403."""
    _, admin_token = admin_user
    target_user, _ = second_user

    await client.patch(
        f"/api/v1/admin/users/{target_user.id}/deactivate",
        headers={"Authorization": f"Bearer {admin_token}"},
    )

    response = await client.post(
        "/api/v1/auth/login",
        json={"email": target_user.email, "password": "password1"},
    )
    assert response.status_code == 403
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_response_shape_on_all_endpoints(
    client: AsyncClient, regular_user: tuple[User, str]
):
    _, token = regular_user
    response = await client.get(
        "/api/v1/users/me", headers={"Authorization": f"Bearer {token}"}
    )
    body = response.json()
    assert "success" in body
    assert "data" in body
    assert "message" in body
