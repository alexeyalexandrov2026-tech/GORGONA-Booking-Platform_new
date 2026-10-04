"""Versioned owner-provided departments; no head, budget or staff assignment is implied."""

from typing import Literal
from uuid import UUID

from pydantic import AwareDatetime, Field, StrictBool, StrictInt, field_validator

from gorgona_booking.business.contracts import Strict


class DepartmentInput(Strict):
    """Full replacement of the current draft: every link is stated, null means none."""

    schema_version: Literal[1] = 1
    expected_revision: StrictInt = Field(ge=0, le=2_147_483_646)
    code: str = Field(min_length=1, max_length=64, pattern=r"^[A-Z0-9][A-Z0-9_-]*$")
    name: str = Field(min_length=1, max_length=200)
    parent_department_id: UUID | None
    legal_entity_id: UUID | None
    location_id: UUID | None
    archived: StrictBool

    @field_validator("schema_version", mode="before")
    @classmethod
    def integer_version(cls, value: object) -> object:
        if type(value) is not int:
            raise ValueError("Version must be an integer")
        return value

    @field_validator("name")
    @classmethod
    def owner_provided_name(cls, value: str) -> str:
        name = value.strip()
        if not name or any(ord(char) < 32 or ord(char) == 127 for char in name):
            raise ValueError("Provide a nonblank department name without control characters")
        return name


class DepartmentView(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    department_id: UUID
    code: str
    name: str
    parent_department_id: UUID | None
    legal_entity_id: UUID | None
    location_id: UUID | None
    archived: bool
    revision: int = Field(ge=1)
    state: Literal["draft"] = "draft"
    created_at: AwareDatetime


class DepartmentList(Strict):
    schema_version: Literal[1] = 1
    business_id: UUID
    items: tuple[DepartmentView, ...]
    next_cursor: str | None
