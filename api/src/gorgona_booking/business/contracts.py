"""Versioned business profile contracts; saving a draft never activates a module."""

from datetime import datetime
from typing import Literal, Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictInt, field_validator, model_validator

from gorgona_booking.business.catalog import CATALOG_VERSION, INDUSTRY_IDS, BusinessFormat


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class Versioned(Strict):
    """A command body whose schema version must be a real integer."""

    schema_version: Literal[1] = 1

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Version must be an integer")
        return value


class ProfileInput(Strict):
    schema_version: Literal[1] = 1
    catalog_version: Literal[1] = CATALOG_VERSION
    expected_revision: StrictInt = Field(ge=0, le=2_147_483_646)
    industry_ids: tuple[StrictInt, ...] = Field(min_length=1, max_length=39)
    business_formats: tuple[BusinessFormat, ...] = Field(default=(), max_length=5)
    custom_activity_name: str | None = Field(default=None, min_length=1, max_length=200)

    @field_validator("schema_version", "catalog_version", mode="before")
    @classmethod
    def require_integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Version must be an integer")
        return value

    @model_validator(mode="after")
    def validate_selections(self) -> Self:
        if set(self.industry_ids) - INDUSTRY_IDS:
            raise ValueError("Unknown industry identifier")
        if len(set(self.industry_ids)) != len(self.industry_ids):
            raise ValueError("Select each industry only once")
        if len(set(self.business_formats)) != len(self.business_formats):
            raise ValueError("Select each business format only once")
        if self.custom_activity_name is not None and not self.custom_activity_name.strip():
            raise ValueError("Activity name cannot be blank")
        return self


class BusinessProfile(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    revision: int = Field(ge=1)
    catalog_version: int
    state: Literal["draft"] = "draft"
    industry_ids: tuple[int, ...]
    business_formats: tuple[BusinessFormat, ...]
    custom_activity_name: str | None
    created_at: datetime


class BusinessLocation(Strict):
    id: UUID
    name: str
    timezone: str


class BusinessView(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    display_name: str
    locations: tuple[BusinessLocation, ...]
    profile: BusinessProfile | None
