"""Schemas for LLM configuration APIs."""

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from codeask.llm.types import ProviderProtocol

DEFAULT_LLM_MAX_TOKENS = 8192
DEFAULT_LLM_TEMPERATURE = 0.2
DEFAULT_OPENCODE_PROVIDER_PROFILE = "default"


class LLMConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    protocol: ProviderProtocol
    base_url: str | None = None
    api_key: str = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1, max_length=128)
    max_tokens: int = Field(default=DEFAULT_LLM_MAX_TOKENS, ge=1)
    temperature: float = Field(default=DEFAULT_LLM_TEMPERATURE, ge=0.0)
    is_default: bool = False
    enabled: bool = True
    rpm_limit: int | None = Field(default=None, ge=1)
    quota_remaining: float | None = Field(default=None, ge=0.0)
    reasoning_profile: str = Field(default="none", max_length=64)
    reasoning_profile_json: str | None = Field(default=None, max_length=4096)
    opencode_provider_profile: str = Field(
        default=DEFAULT_OPENCODE_PROVIDER_PROFILE,
        max_length=128,
    )


class LLMConfigUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    protocol: ProviderProtocol | None = None
    base_url: str | None = None
    api_key: str | None = Field(default=None, min_length=1)
    model_name: str | None = Field(default=None, min_length=1, max_length=128)
    max_tokens: int | None = Field(default=None, ge=1)
    temperature: float | None = Field(default=None, ge=0.0)
    is_default: bool | None = None
    enabled: bool | None = None
    rpm_limit: int | None = Field(default=None, ge=1)
    quota_remaining: float | None = Field(default=None, ge=0.0)
    reasoning_profile: str | None = Field(default=None, max_length=64)
    reasoning_profile_json: str | None = Field(default=None, max_length=4096)
    opencode_provider_profile: str | None = Field(default=None, max_length=128)
    opencode_provider_status: str | None = Field(default=None, max_length=16)
    opencode_provider_tested_at: datetime | None = None
    opencode_provider_error: str | None = Field(default=None, max_length=2000)
    opencode_provider_test_result_json: object | None = None


class LLMConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    scope: str
    owner_subject_id: str | None
    protocol: str
    base_url: str | None
    api_key_masked: str
    model_name: str
    max_tokens: int
    temperature: float
    is_default: bool
    enabled: bool
    rpm_limit: int | None
    quota_remaining: float | None
    reasoning_profile: str
    reasoning_profile_json: str | None
    opencode_provider_profile: str | None
    opencode_provider_status: str
    opencode_provider_tested_at: datetime | None
    opencode_provider_error: str | None
    opencode_provider_test_result_json: object | None


class LLMConfigTestResponse(BaseModel):
    status: str
    profile_id: str | None = None
    provider_npm: str | None = None
    text_preview: str | None = None
    error: str | None = None
    tested_at: datetime
    result: object | None = None
