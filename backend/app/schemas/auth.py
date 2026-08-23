"""Auth request/response schemas."""

from __future__ import annotations

from pydantic import BaseModel, EmailStr, Field


class RegisterRequest(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=128)
    name: str = Field(min_length=1, max_length=255)


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class AuthTokens(BaseModel):
    access_token: str
    refresh_token: str


class UserResponse(BaseModel):
    id: str
    email: str
    name: str


class AuthResponse(BaseModel):
    user: UserResponse
    tokens: AuthTokens
