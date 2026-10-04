"""Versioned owner-provided legal-entity drafts; no registration or payment approval."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictInt, field_validator

from gorgona_booking.business.contracts import Strict


class LegalEntityInput(Strict):
    schema_version: Literal[1] = 1
    expected_revision: StrictInt = Field(ge=0, le=2_147_483_646)
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    legal_name: str = Field(min_length=1, max_length=200)

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Version must be an integer")
        return value

    @field_validator("legal_name")
    @classmethod
    def owner_provided_name(cls, value: str) -> str:
        name = value.strip()
        if not name or any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise ValueError("Provide a nonblank legal name without control characters")
        return name


class LegalEntityView(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    legal_entity_id: UUID
    code: str
    legal_name: str
    revision: int = Field(ge=1)
    state: Literal["draft"] = "draft"
    created_at: AwareDatetime


class LegalEntityList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    items: tuple[LegalEntityView, ...]
    next_cursor: str | None
