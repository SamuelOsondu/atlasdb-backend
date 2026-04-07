import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator


class DomainCreateRequest(BaseModel):
    name: str
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Domain name cannot be empty")
        if len(v) > 255:
            raise ValueError("Domain name cannot exceed 255 characters")
        return v


class DomainUpdateRequest(BaseModel):
    name: str | None = None
    description: str | None = None

    @field_validator("name")
    @classmethod
    def validate_name(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.strip()
            if not v:
                raise ValueError("Domain name cannot be empty")
            if len(v) > 255:
                raise ValueError("Domain name cannot exceed 255 characters")
        return v


class DomainResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    owner_id: uuid.UUID
    name: str
    description: str | None
    created_at: datetime
    updated_at: datetime
