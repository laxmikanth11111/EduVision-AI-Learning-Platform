from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field

from shared.constants import UserRole


class UserResponse(BaseModel):
    user_id: str
    email: str
    name: str
    role: UserRole
    is_verified: bool
    is_active: bool
    avatar_url: str | None
    bio: str | None
    created_at: datetime
    last_login_at: datetime | None


class UpdateProfileRequest(BaseModel):
    name: str | None = Field(None, min_length=1, max_length=255)
    avatar_url: str | None = Field(None, max_length=500)
    bio: str | None = Field(None, max_length=2000)


class UpdateProfileResponse(BaseModel):
    user_id: str
    email: str
    name: str
    role: UserRole
    avatar_url: str | None
    bio: str | None
