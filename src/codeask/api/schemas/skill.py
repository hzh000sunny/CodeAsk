"""Schemas for prompt skill APIs."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class SkillCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=128)
    scope: Literal["global", "feature"]
    feature_id: int | None = None
    prompt_template: str = Field(..., min_length=1)

    @model_validator(mode="after")
    def _validate_scope(self) -> "SkillCreate":
        if self.scope == "global" and self.feature_id is not None:
            raise ValueError("global skills must not set feature_id")
        if self.scope == "feature" and self.feature_id is None:
            raise ValueError("feature skills require feature_id")
        return self


class SkillUpdate(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=128)
    prompt_template: str | None = Field(default=None, min_length=1)


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    scope: str
    feature_id: int | None
    prompt_template: str
