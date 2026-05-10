"""Schemas for user APIs."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    username: str
    role: str
    created_at: datetime
    updated_at: datetime
    last_login_at: datetime | None


class UserCandidateResponse(BaseModel):
    id: str
    username: str


class UserUpdate(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)

    @field_validator("username")
    @classmethod
    def strip_username(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("username cannot be empty")
        return cleaned


class PasswordUpdate(BaseModel):
    password: str = Field(..., min_length=1)

    @field_validator("password")
    @classmethod
    def strip_password(cls, value: str) -> str:
        cleaned = value.strip()
        if len(cleaned) < 6:
            raise ValueError("password must be at least 6 characters")
        return cleaned
