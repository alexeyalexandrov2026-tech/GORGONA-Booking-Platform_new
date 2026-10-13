"""Strict version-one inventory contracts of J1: materials and storage places, no money."""

from typing import Annotated, Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

type Label = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=200, pattern=r"^[^\x00-\x1f\x7f]+$"
    ),
]
type Unit = Annotated[
    str,
    StringConstraints(
        strip_whitespace=True, min_length=1, max_length=16, pattern=r"^[^\x00-\x1f\x7f]+$"
    ),
]
type Code = Annotated[str, StringConstraints(pattern=r"^[A-Z0-9][A-Z0-9_-]{0,63}$")]


class InventoryModel(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)
    schema_version: Literal[1] = 1


class RevisionInput(InventoryModel):
    expected_revision: int = Field(ge=0, le=2147483646)


class ItemInput(RevisionInput):
    code: Code
    name: Label
    # A label the business types; units are never converted.
    unit: Unit
    # Decimal places of a quantity of this material.
    quantity_scale: int = Field(ge=0, le=3)
    archived: bool = False


class ItemView(InventoryModel):
    business_id: UUID
    item_id: UUID
    code: str
    unit: str
    quantity_scale: int
    revision: int
    name: str
    archived: bool


class PlaceInput(RevisionInput):
    location_id: UUID
    code: Code
    name: Label
    archived: bool = False


class PlaceView(InventoryModel):
    business_id: UUID
    place_id: UUID
    location_id: UUID
    code: str
    revision: int
    name: str
    archived: bool


class InventoryReceipt(InventoryModel):
    subject_id: UUID
    revision: int = 0


class ItemList(InventoryModel):
    items: tuple[ItemView, ...]
    next_cursor: UUID | None = None


class PlaceList(InventoryModel):
    items: tuple[PlaceView, ...]
    next_cursor: UUID | None = None
