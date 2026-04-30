"""Schemas for LLM configuration APIs."""

from pydantic import BaseModel, ConfigDict, Field

from codeask.llm.types import ProviderProtocol


class LLMConfigCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    protocol: ProviderProtocol
    base_url: str | None = None
    api_key: str = Field(..., min_length=1)
    model_name: str = Field(..., min_length=1, max_length=128)
    max_tokens: int = Field(..., ge=1)
    temperature: float = Field(..., ge=0.0)
    is_default: bool = False


class LLMConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    protocol: str
    base_url: str | None
    api_key_masked: str
    model_name: str
    max_tokens: int
    temperature: float
    is_default: bool
