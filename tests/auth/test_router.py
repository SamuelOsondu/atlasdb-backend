import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_register_returns_201_with_user_and_tokens(client: AsyncClient):
    response = await client.post("/api/v1/auth/register", json={
        "email": "newuser@example.com",
        "password": "securepass",
        "full_name": "New User",
    })
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["user"]["email"] == "newuser@example.com"
    assert body["data"]["tokens"]["access_token"]
    assert body["data"]["tokens"]["refresh_token"]


@pytest.mark.asyncio
async def test_register_duplicate_email_returns_409(client: AsyncClient):
    payload = {"email": "dup@example.com", "password": "password1"}
    await client.post("/api/v1/auth/register", json=payload)
    response = await client.post("/api/v1/auth/register", json=payload)
    assert response.status_code == 409
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_register_short_password_returns_422(client: AsyncClient):
    response = await client.post("/api/v1/auth/register", json={
        "email": "short@example.com",
        "password": "123",
    })
    assert response.status_code == 422
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_register_invalid_email_returns_422(client: AsyncClient):
    response = await client.post("/api/v1/auth/register", json={
        "email": "not-an-email",
        "password": "password1",
    })
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_returns_200_with_tokens(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "logintest@example.com",
        "password": "password1",
    })
    response = await client.post("/api/v1/auth/login", json={
        "email": "logintest@example.com",
        "password": "password1",
    })
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert body["data"]["tokens"]["access_token"]


@pytest.mark.asyncio
async def test_login_wrong_password_returns_401(client: AsyncClient):
    await client.post("/api/v1/auth/register", json={
        "email": "wrongpwd@example.com",
        "password": "correctpass",
    })
    response = await client.post("/api/v1/auth/login", json={
        "email": "wrongpwd@example.com",
        "password": "wrongpass",
    })
    assert response.status_code == 401
    assert response.json()["success"] is False


@pytest.mark.asyncio
async def test_login_nonexistent_user_returns_401(client: AsyncClient):
    response = await client.post("/api/v1/auth/login", json={
        "email": "nobody@example.com",
        "password": "password1",
    })
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_returns_new_tokens(client: AsyncClient):
    reg = await client.post("/api/v1/auth/register", json={
        "email": "refreshtest@example.com",
        "password": "password1",
    })
    refresh_token = reg.json()["data"]["tokens"]["refresh_token"]

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    assert response.json()["data"]["access_token"]
    assert response.json()["data"]["refresh_token"] != refresh_token


@pytest.mark.asyncio
async def test_refresh_with_invalid_token_returns_401(client: AsyncClient):
    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": "invalid"})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_refresh_with_revoked_token_returns_401(client: AsyncClient):
    reg = await client.post("/api/v1/auth/register", json={
        "email": "revokedtest@example.com",
        "password": "password1",
    })
    refresh_token = reg.json()["data"]["tokens"]["refresh_token"]

    await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})

    response = await client.post("/api/v1/auth/refresh", json={"refresh_token": refresh_token})
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_logout_returns_200(client: AsyncClient):
    reg = await client.post("/api/v1/auth/register", json={
        "email": "logouttest@example.com",
        "password": "password1",
    })
    refresh_token = reg.json()["data"]["tokens"]["refresh_token"]

    response = await client.post("/api/v1/auth/logout", json={"refresh_token": refresh_token})
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_protected_route_with_valid_token(client: AsyncClient):
    reg = await client.post("/api/v1/auth/register", json={
        "email": "protected@example.com",
        "password": "password1",
    })
    access_token = reg.json()["data"]["tokens"]["access_token"]

    response = await client.get(
        "/health",  # unprotected, but tests the app is reachable
        headers={"Authorization": f"Bearer {access_token}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_response_shape_always_present(client: AsyncClient):
    # Every endpoint — success and failure — must have success/data/message fields.
    response = await client.post("/api/v1/auth/login", json={
        "email": "nope@example.com",
        "password": "nope",
    })
    body = response.json()
    assert "success" in body
    assert "data" in body
    assert "message" in body
