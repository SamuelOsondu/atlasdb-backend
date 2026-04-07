"""
Router-layer (HTTP integration) tests for the documents component.

Storage is replaced with InMemoryStorage via FastAPI dependency override so
no disk I/O occurs. Celery enqueue is silently skipped because the processing
component is not yet implemented.
"""
import io
import uuid

import pytest
from httpx import AsyncClient

from app.core.dependencies import get_storage_dep
from app.documents.models import Document
from app.domains.models import KnowledgeDomain
from app.shared.enums import DocumentStatus
from app.users.models import User
from tests.documents.conftest import InMemoryStorage


# ── helpers ────────────────────────────────────────────────────────────────────

def _pdf_files(content: bytes = b"fake pdf", filename: str = "doc.pdf"):
    return {"file": (filename, io.BytesIO(content), "application/pdf")}


def _txt_files(content: bytes = b"hello world", filename: str = "doc.txt"):
    return {"file": (filename, io.BytesIO(content), "text/plain")}


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ── POST /domains/{domain_id}/documents ────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_returns_201(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    mock_storage: InMemoryStorage,
):
    from app.main import app
    app.dependency_overrides[get_storage_dep] = lambda: mock_storage

    _, token = user_with_token
    response = await client.post(
        f"/api/v1/domains/{domain.id}/documents",
        headers=_auth(token),
        files=_pdf_files(),
    )
    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["status"] == DocumentStatus.pending.value
    assert body["data"]["mime_type"] == "application/pdf"

    app.dependency_overrides.pop(get_storage_dep, None)


@pytest.mark.asyncio
async def test_upload_with_explicit_title(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    mock_storage: InMemoryStorage,
):
    from app.main import app
    app.dependency_overrides[get_storage_dep] = lambda: mock_storage

    _, token = user_with_token
    response = await client.post(
        f"/api/v1/domains/{domain.id}/documents",
        headers=_auth(token),
        files=_txt_files(),
        data={"title": "My Custom Title"},
    )
    assert response.status_code == 201
    assert response.json()["data"]["title"] == "My Custom Title"

    app.dependency_overrides.pop(get_storage_dep, None)


@pytest.mark.asyncio
async def test_upload_requires_auth(
    client: AsyncClient,
    domain: KnowledgeDomain,
):
    response = await client.post(
        f"/api/v1/domains/{domain.id}/documents",
        files=_pdf_files(),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_upload_rejects_unsupported_type(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    mock_storage: InMemoryStorage,
):
    from app.main import app
    app.dependency_overrides[get_storage_dep] = lambda: mock_storage

    _, token = user_with_token
    response = await client.post(
        f"/api/v1/domains/{domain.id}/documents",
        headers=_auth(token),
        files={"file": ("page.html", io.BytesIO(b"<html>"), "text/html")},
    )
    assert response.status_code == 422

    app.dependency_overrides.pop(get_storage_dep, None)


@pytest.mark.asyncio
async def test_upload_to_foreign_domain_returns_404(
    client: AsyncClient,
    other_user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    mock_storage: InMemoryStorage,
):
    from app.main import app
    app.dependency_overrides[get_storage_dep] = lambda: mock_storage

    _, token = other_user_with_token
    response = await client.post(
        f"/api/v1/domains/{domain.id}/documents",
        headers=_auth(token),
        files=_pdf_files(),
    )
    assert response.status_code == 404

    app.dependency_overrides.pop(get_storage_dep, None)


@pytest.mark.asyncio
async def test_upload_file_too_large_returns_413(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    mock_storage: InMemoryStorage,
    monkeypatch,
):
    from app.core import config as config_mod
    monkeypatch.setattr(config_mod.settings, "MAX_FILE_SIZE_MB", 1)

    from app.main import app
    app.dependency_overrides[get_storage_dep] = lambda: mock_storage

    _, token = user_with_token
    oversized = b"x" * (1 * 1024 * 1024 + 1)
    response = await client.post(
        f"/api/v1/domains/{domain.id}/documents",
        headers=_auth(token),
        files={"file": ("big.pdf", io.BytesIO(oversized), "application/pdf")},
    )
    assert response.status_code == 413

    app.dependency_overrides.pop(get_storage_dep, None)


@pytest.mark.asyncio
async def test_upload_to_nonexistent_domain_returns_404(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    mock_storage: InMemoryStorage,
):
    from app.main import app
    app.dependency_overrides[get_storage_dep] = lambda: mock_storage

    _, token = user_with_token
    response = await client.post(
        f"/api/v1/domains/{uuid.uuid4()}/documents",
        headers=_auth(token),
        files=_pdf_files(),
    )
    assert response.status_code == 404

    app.dependency_overrides.pop(get_storage_dep, None)


# ── GET /domains/{domain_id}/documents ─────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_documents_returns_paginated(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    document: Document,
):
    _, token = user_with_token
    response = await client.get(
        f"/api/v1/domains/{domain.id}/documents",
        headers=_auth(token),
    )
    assert response.status_code == 200
    body = response.json()
    assert body["success"] is True
    assert isinstance(body["data"], list)
    assert "pagination" in body
    assert body["pagination"]["total"] >= 1


@pytest.mark.asyncio
async def test_list_documents_excludes_deleted(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    document: Document,
):
    _, token = user_with_token
    # Delete the document first.
    await client.delete(f"/api/v1/documents/{document.id}", headers=_auth(token))

    response = await client.get(
        f"/api/v1/domains/{domain.id}/documents",
        headers=_auth(token),
    )
    ids = [d["id"] for d in response.json()["data"]]
    assert str(document.id) not in ids


@pytest.mark.asyncio
async def test_list_documents_foreign_domain_returns_404(
    client: AsyncClient,
    other_user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
):
    _, token = other_user_with_token
    response = await client.get(
        f"/api/v1/domains/{domain.id}/documents",
        headers=_auth(token),
    )
    assert response.status_code == 404


# ── GET /documents/{document_id} ───────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_document_returns_200(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    document: Document,
):
    _, token = user_with_token
    response = await client.get(
        f"/api/v1/documents/{document.id}",
        headers=_auth(token),
    )
    assert response.status_code == 200
    assert response.json()["data"]["id"] == str(document.id)


@pytest.mark.asyncio
async def test_get_document_foreign_returns_404(
    client: AsyncClient,
    other_user_with_token: tuple[User, str],
    document: Document,
):
    _, token = other_user_with_token
    response = await client.get(
        f"/api/v1/documents/{document.id}",
        headers=_auth(token),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_document_nonexistent_returns_404(
    client: AsyncClient,
    user_with_token: tuple[User, str],
):
    _, token = user_with_token
    response = await client.get(
        f"/api/v1/documents/{uuid.uuid4()}",
        headers=_auth(token),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_get_document_deleted_returns_404(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    document: Document,
):
    _, token = user_with_token
    await client.delete(f"/api/v1/documents/{document.id}", headers=_auth(token))
    response = await client.get(
        f"/api/v1/documents/{document.id}",
        headers=_auth(token),
    )
    assert response.status_code == 404


# ── DELETE /documents/{document_id} ────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_document_returns_200(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    document: Document,
):
    _, token = user_with_token
    response = await client.delete(
        f"/api/v1/documents/{document.id}",
        headers=_auth(token),
    )
    assert response.status_code == 200
    assert response.json()["success"] is True


@pytest.mark.asyncio
async def test_delete_document_removes_from_list(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    document: Document,
):
    _, token = user_with_token
    await client.delete(f"/api/v1/documents/{document.id}", headers=_auth(token))
    response = await client.get(
        f"/api/v1/domains/{domain.id}/documents",
        headers=_auth(token),
    )
    ids = [d["id"] for d in response.json()["data"]]
    assert str(document.id) not in ids


@pytest.mark.asyncio
async def test_delete_document_foreign_returns_404(
    client: AsyncClient,
    other_user_with_token: tuple[User, str],
    document: Document,
):
    _, token = other_user_with_token
    response = await client.delete(
        f"/api/v1/documents/{document.id}",
        headers=_auth(token),
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_delete_processing_document_returns_409(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    processing_document: Document,
):
    _, token = user_with_token
    response = await client.delete(
        f"/api/v1/documents/{processing_document.id}",
        headers=_auth(token),
    )
    assert response.status_code == 409


# ── POST /admin/documents/{id}/reprocess ───────────────────────────────────────

@pytest.mark.asyncio
async def test_admin_reprocess_returns_200(
    client: AsyncClient,
    admin_user_with_token: tuple[User, str],
    indexed_document: Document,
):
    _, token = admin_user_with_token
    response = await client.post(
        f"/api/v1/admin/documents/{indexed_document.id}/reprocess",
        headers=_auth(token),
    )
    assert response.status_code == 200
    assert response.json()["data"]["status"] == DocumentStatus.pending.value


@pytest.mark.asyncio
async def test_admin_reprocess_requires_admin(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    indexed_document: Document,
):
    _, token = user_with_token
    response = await client.post(
        f"/api/v1/admin/documents/{indexed_document.id}/reprocess",
        headers=_auth(token),
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_admin_reprocess_can_access_any_owners_document(
    client: AsyncClient,
    admin_user_with_token: tuple[User, str],
    indexed_document: Document,
):
    """Admin can reprocess documents from any owner, not just their own."""
    _, token = admin_user_with_token
    response = await client.post(
        f"/api/v1/admin/documents/{indexed_document.id}/reprocess",
        headers=_auth(token),
    )
    assert response.status_code == 200


# ── response shape ─────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_upload_response_shape(
    client: AsyncClient,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
    mock_storage: InMemoryStorage,
):
    from app.main import app
    app.dependency_overrides[get_storage_dep] = lambda: mock_storage

    _, token = user_with_token
    response = await client.post(
        f"/api/v1/domains/{domain.id}/documents",
        headers=_auth(token),
        files=_pdf_files(),
    )
    body = response.json()
    assert "success" in body
    assert "data" in body
    assert "message" in body
    data = body["data"]
    for field in ("id", "owner_id", "domain_id", "title", "status", "mime_type", "file_size"):
        assert field in data, f"Missing field: {field}"

    app.dependency_overrides.pop(get_storage_dep, None)
