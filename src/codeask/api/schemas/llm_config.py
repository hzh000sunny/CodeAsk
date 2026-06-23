"""Schemas for LLM configuration APIs."""

import re
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator

from codeask.llm.types import LLMConfigMode

# Mirrors opencode's custom-provider slug rule (dialog-custom-provider-form.ts).
_PROVIDER_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-_]*$")


def _validate_provider_id(value: str) -> str:
    if not _PROVIDER_ID_RE.match(value):
        raise ValueError("provider_id must match ^[a-z0-9][a-z0-9-_]*$")
    return value


class LLMConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    mode: LLMConfigMode = "catalog"
    provider_id: str = Field(..., min_length=1, max_length=128)
    base_url: str | None = None
    api_key: str = Field(..., min_length=1)
    headers: dict[str, str] | None = None
    model_name: str = Field(..., min_length=1, max_length=128)
    is_default: bool = False
    enabled: bool = True
    reasoning_profile: str = Field(default="none", max_length=64)
    reasoning_profile_json: str | None = Field(default=None, max_length=4096)
    opencode_provider_status: str | None = Field(default=None, max_length=16)
    opencode_provider_tested_at: datetime | None = None
    opencode_provider_error: str | None = Field(default=None, max_length=2000)
    opencode_provider_test_result_json: object | None = None

    @field_validator("provider_id")
    @classmethod
    def _check_provider_id(cls, value: str) -> str:
        return _validate_provider_id(value)


class LLMConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    mode: LLMConfigMode | None = None
    provider_id: str | None = Field(default=None, min_length=1, max_length=128)
    base_url: str | None = None
    api_key: str | None = Field(default=None, min_length=1)
    headers: dict[str, str] | None = None
    model_name: str | None = Field(default=None, min_length=1, max_length=128)
    is_default: bool | None = None
    enabled: bool | None = None
    reasoning_profile: str | None = Field(default=None, max_length=64)
    reasoning_profile_json: str | None = Field(default=None, max_length=4096)
    opencode_provider_status: str | None = Field(default=None, max_length=16)
    opencode_provider_tested_at: datetime | None = None
    opencode_provider_error: str | None = Field(default=None, max_length=2000)
    opencode_provider_test_result_json: object | None = None

    @field_validator("provider_id")
    @classmethod
    def _check_provider_id(cls, value: str | None) -> str | None:
        return _validate_provider_id(value) if value is not None else None


class LLMConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    scope: str
    owner_subject_id: str | None
    mode: str
    provider_id: str
    base_url: str | None
    api_key_masked: str
    headers_masked: dict[str, str] = Field(default_factory=dict)
    model_name: str
    is_default: bool
    enabled: bool
    reasoning_profile: str
    reasoning_profile_json: str | None
    agent_runtime_backend: str
    agent_runtime_status: str
    agent_runtime_tested_at: datetime | None
    agent_runtime_error: str | None
    agent_runtime_test_result_json: object | None
    opencode_provider_status: str
    opencode_provider_tested_at: datetime | None
    opencode_provider_error: str | None
    opencode_provider_test_result_json: object | None


class LLMConfigTestResponse(BaseModel):
    status: str
    provider_id: str | None = None
    model_id: str | None = None
    text_preview: str | None = None
    error: str | None = None
    tested_at: datetime
    result: object | None = None


class LLMProviderResponse(BaseModel):
    id: str
    name: str


class LLMProvidersResponse(BaseModel):
    providers: list[LLMProviderResponse]
