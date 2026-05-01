"""Schemas for LLM configuration APIs."""

from pydantic import BaseModel, ConfigDict, Field

from codeask.llm.types import ProviderProtocol

DEFAULT_LLM_MAX_TOKENS = 200 * 1024
DEFAULT_LLM_TEMPERATURE = 0.2


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
