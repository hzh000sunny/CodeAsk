"""Schemas for authentication APIs."""

from __future__ import annotations

from pydantic import BaseModel, Field, field_validator


class AuthMeResponse(BaseModel):
    subject_id: str
    display_name: str
    role: str
    authenticated: bool


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=1, max_length=128)
    password: str = Field(..., min_length=1)

    @field_validator("username")
    @classmethod
    def strip_username(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("username cannot be empty")
        return cleaned

    @field_validator("password")
    @classmethod
    def strip_password(cls, value: str) -> str:
        return value.strip()


class AdminLoginRequest(BaseModel):
    username: str = Field(default="admin", min_length=1)
    password: str = Field(..., min_length=1)

    @field_validator("username", "password")
    @classmethod
    def strip_value(cls, value: str) -> str:
        return value.strip()
