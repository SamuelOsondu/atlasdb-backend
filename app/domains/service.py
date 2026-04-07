import uuid
from datetime import datetime, timezone

from sqlalchemy import func, select, update as sa_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import AppValidationError, ConflictError, NotFoundError
from app.domains.models import KnowledgeDomain
from app.domains.schemas import DomainCreateRequest, DomainUpdateRequest


async def get_domain_or_404(
    domain_id: uuid.UUID,
    owner_id: uuid.UUID,
    db: AsyncSession,
) -> KnowledgeDomain:
    """
    Fetch a domain by ID and owner. Returns 404 for both non-existent and
    foreign domains — prevents enumeration of other users' domain IDs.
    Used as the shared ownership-enforcement helper by documents and retrieval.
    """
    result = await db.execute(
        select(KnowledgeDomain).where(
            KnowledgeDomain.id == domain_id,
            KnowledgeDomain.owner_id == owner_id,
        )
    )
    domain = result.scalar_one_or_none()
    if domain is None:
        raise NotFoundError("Domain not found")
    return domain


async def create_domain(
    data: DomainCreateRequest,
    owner_id: uuid.UUID,
    db: AsyncSession,
) -> KnowledgeDomain:
    domain = KnowledgeDomain(
        owner_id=owner_id,
        name=data.name,
        description=data.description,
    )
    db.add(domain)
    try:
        await db.flush()
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(f"A domain named '{data.name}' already exists")
    await db.refresh(domain)
    return domain


async def list_domains(
    owner_id: uuid.UUID,
    page: int,
    page_size: int,
    db: AsyncSession,
) -> tuple[list[KnowledgeDomain], int]:
    offset = (page - 1) * page_size

    total: int = (
        await db.execute(
            select(func.count())
            .select_from(KnowledgeDomain)
            .where(KnowledgeDomain.owner_id == owner_id)
        )
    ).scalar_one()

    domains = list(
        (
            await db.execute(
                select(KnowledgeDomain)
                .where(KnowledgeDomain.owner_id == owner_id)
                .order_by(KnowledgeDomain.created_at.desc())
                .offset(offset)
                .limit(page_size)
            )
        ).scalars()
    )
    return domains, total


async def update_domain(
    domain: KnowledgeDomain,
    data: DomainUpdateRequest,
    db: AsyncSession,
) -> KnowledgeDomain:
    fields_set = data.model_fields_set
    updated = False

    # name=None with field omitted means "don't change"; null is invalid for name.
    if "name" in fields_set and data.name is not None:
        domain.name = data.name
        updated = True

    # description=None explicitly clears it; omitting leaves it unchanged.
    if "description" in fields_set:
        domain.description = data.description
        updated = True

    if not updated:
        raise AppValidationError("No fields to update")

    domain.updated_at = datetime.now(timezone.utc)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise ConflictError(f"A domain named '{data.name}' already exists")

    await db.refresh(domain)
    return domain


async def delete_domain(domain: KnowledgeDomain, db: AsyncSession) -> None:
    """
    Deletes a domain. Cascade soft-deletes all documents belonging to it first,
    atomically within the same transaction.

    The document cascade uses a deferred import so this function works correctly
    before the documents component is implemented. Once app.documents.models
    exists the import resolves and the cascade runs on every delete.
    """
    try:
        from app.documents.models import Document  # noqa: PLC0415
        await db.execute(
            sa_update(Document)
            .where(Document.domain_id == domain.id, Document.deleted_at.is_(None))
            .values(deleted_at=datetime.now(timezone.utc))
        )
    except ImportError:
        pass  # Documents component not yet implemented; cascade added when available.

    await db.delete(domain)
    await db.commit()
