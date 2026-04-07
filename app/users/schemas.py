import uuid
from datetime import datetime

from pydantic import BaseModel, ConfigDict, field_validator, model_validator


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: uuid.UUID
    email: str
    full_name: str | None
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: datetime


class UpdateProfileRequest(BaseModel):
    """
    Handles both profile field updates and password changes in one request.
    - Omit `full_name` entirely to leave it unchanged; set to null to clear it.
    - Provide both `current_password` and `new_password` to change password.
    """

    full_name: str | None = None
    current_password: str | None = None
    new_password: str | None = None

    @field_validator("new_password")
    @classmethod
    def validate_new_password_length(cls, v: str | None) -> str | None:
        if v is not None and len(v) < 8:
            raise ValueError("new_password must be at least 8 characters")
        return v

    @model_validator(mode="after")
    def validate_password_pair(self) -> "UpdateProfileRequest":
        has_current = self.current_password is not None
        has_new = self.new_password is not None
        if has_current != has_new:
            raise ValueError(
                "current_password and new_password must be provided together"
            )
        return self
