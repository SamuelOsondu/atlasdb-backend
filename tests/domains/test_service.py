import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.schemas import RegisterRequest
from app.auth.service import register_user
from app.core.exceptions import AppValidationError, ConflictError, NotFoundError
from app.domains.models import KnowledgeDomain
from app.domains.schemas import DomainCreateRequest, DomainUpdateRequest
from app.domains.service import (
    create_domain,
    delete_domain,
    get_domain_or_404,
    list_domains,
    update_domain,
)
from app.users.models import User


# ── create ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_create_domain_returns_domain(db_session: AsyncSession, user_with_token: tuple[User, str]):
    owner, _ = user_with_token
    domain = await create_domain(
        DomainCreateRequest(name="Support Playbooks", description="CS runbooks"),
        owner.id,
        db_session,
    )
    assert domain.id is not None
    assert domain.name == "Support Playbooks"
    assert domain.description == "CS runbooks"
    assert domain.owner_id == owner.id


@pytest.mark.asyncio
async def test_create_domain_without_description(db_session: AsyncSession, user_with_token: tuple[User, str]):
    owner, _ = user_with_token
    domain = await create_domain(
        DomainCreateRequest(name="Minimal Domain"),
        owner.id,
        db_session,
    )
    assert domain.description is None


@pytest.mark.asyncio
async def test_create_domain_rejects_duplicate_name_same_owner(
    db_session: AsyncSession, user_with_token: tuple[User, str]
):
    owner, _ = user_with_token
    await create_domain(DomainCreateRequest(name="Duplicate"), owner.id, db_session)
    with pytest.raises(ConflictError):
        await create_domain(DomainCreateRequest(name="Duplicate"), owner.id, db_session)


@pytest.mark.asyncio
async def test_create_domain_allows_same_name_for_different_owners(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    other_user_with_token: tuple[User, str],
):
    owner_a, _ = user_with_token
    owner_b, _ = other_user_with_token
    await create_domain(DomainCreateRequest(name="Shared Name"), owner_a.id, db_session)
    # Must not raise — uniqueness is per owner
    domain_b = await create_domain(DomainCreateRequest(name="Shared Name"), owner_b.id, db_session)
    assert domain_b.owner_id == owner_b.id


# ── get_domain_or_404 ─────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_get_domain_or_404_returns_own_domain(
    db_session: AsyncSession,
    domain: KnowledgeDomain,
    user_with_token: tuple[User, str],
):
    owner, _ = user_with_token
    fetched = await get_domain_or_404(domain.id, owner.id, db_session)
    assert fetched.id == domain.id


@pytest.mark.asyncio
async def test_get_domain_or_404_raises_for_nonexistent(db_session: AsyncSession, user_with_token: tuple[User, str]):
    owner, _ = user_with_token
    with pytest.raises(NotFoundError):
        await get_domain_or_404(uuid.uuid4(), owner.id, db_session)


@pytest.mark.asyncio
async def test_get_domain_or_404_raises_for_foreign_domain(
    db_session: AsyncSession,
    domain: KnowledgeDomain,
    other_user_with_token: tuple[User, str],
):
    """A domain belonging to user A must not be accessible by user B — returns 404 not 403."""
    other_owner, _ = other_user_with_token
    with pytest.raises(NotFoundError):
        await get_domain_or_404(domain.id, other_owner.id, db_session)


# ── list ──────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_list_domains_returns_only_own(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    other_user_with_token: tuple[User, str],
):
    owner, _ = user_with_token
    other, _ = other_user_with_token
    await create_domain(DomainCreateRequest(name="Owner Domain"), owner.id, db_session)
    await create_domain(DomainCreateRequest(name="Other Domain"), other.id, db_session)

    domains, total = await list_domains(owner.id, page=1, page_size=100, db=db_session)
    emails = {d.owner_id for d in domains}
    assert other.id not in emails
    assert all(d.owner_id == owner.id for d in domains)


@pytest.mark.asyncio
async def test_list_domains_pagination(db_session: AsyncSession, user_with_token: tuple[User, str]):
    owner, _ = user_with_token
    for i in range(5):
        await create_domain(DomainCreateRequest(name=f"Domain {i}"), owner.id, db_session)

    domains, total = await list_domains(owner.id, page=1, page_size=2, db=db_session)
    assert len(domains) == 2
    assert total >= 5


@pytest.mark.asyncio
async def test_list_domains_empty(db_session: AsyncSession):
    user, _ = await register_user(
        RegisterRequest(email="nodomains@example.com", password="password1"), db_session
    )
    domains, total = await list_domains(user.id, page=1, page_size=20, db=db_session)
    assert domains == []
    assert total == 0


# ── update ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_update_domain_name(
    db_session: AsyncSession,
    domain: KnowledgeDomain,
):
    updated = await update_domain(domain, DomainUpdateRequest(name="New Name"), db_session)
    assert updated.name == "New Name"


@pytest.mark.asyncio
async def test_update_domain_description(
    db_session: AsyncSession,
    domain: KnowledgeDomain,
):
    updated = await update_domain(
        domain, DomainUpdateRequest.model_validate({"description": "Updated desc"}), db_session
    )
    assert updated.description == "Updated desc"


@pytest.mark.asyncio
async def test_update_domain_clears_description(
    db_session: AsyncSession,
    domain: KnowledgeDomain,
):
    updated = await update_domain(
        domain, DomainUpdateRequest.model_validate({"description": None}), db_session
    )
    assert updated.description is None


@pytest.mark.asyncio
async def test_update_domain_empty_body_raises(
    db_session: AsyncSession,
    domain: KnowledgeDomain,
):
    with pytest.raises(AppValidationError):
        await update_domain(domain, DomainUpdateRequest(), db_session)


@pytest.mark.asyncio
async def test_update_domain_duplicate_name_raises(
    db_session: AsyncSession,
    user_with_token: tuple[User, str],
    domain: KnowledgeDomain,
):
    owner, _ = user_with_token
    await create_domain(DomainCreateRequest(name="Existing Name"), owner.id, db_session)
    with pytest.raises(ConflictError):
        await update_domain(domain, DomainUpdateRequest(name="Existing Name"), db_session)


# ── delete ────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_delete_domain_removes_it(
    db_session: AsyncSession,
    domain: KnowledgeDomain,
    user_with_token: tuple[User, str],
):
    owner, _ = user_with_token
    await delete_domain(domain, db_session)
    with pytest.raises(NotFoundError):
        await get_domain_or_404(domain.id, owner.id, db_session)


@pytest.mark.asyncio
async def test_delete_domain_does_not_affect_other_domains(
    db_session: AsyncSession,
    domain: KnowledgeDomain,
    user_with_token: tuple[User, str],
):
    owner, _ = user_with_token
    other = await create_domain(DomainCreateRequest(name="Keep This"), owner.id, db_session)
    await delete_domain(domain, db_session)
    fetched = await get_domain_or_404(other.id, owner.id, db_session)
    assert fetched.id == other.id
