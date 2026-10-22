"""Catalog value types. Money is integer cents with an explicit ISO currency."""

from dataclasses import dataclass, field
from typing import Literal
from uuid import UUID

type CatalogStatus = Literal["draft", "published", "archived"]
# L1 (package L): what a stage of a service does, and which resource kinds it occupies.
type StageKind = Literal["active", "processing", "finish"]
type StageResource = Literal["specialist", "chair", "room", "equipment"]


@dataclass(frozen=True, slots=True)
class StageSpec:
    kind: StageKind
    minutes: int
    resources: tuple[StageResource, ...]


@dataclass(frozen=True, slots=True)
class VariantSpec:
    id: UUID
    code: str
    name: str
    status: CatalogStatus
    price_cents: int
    currency: str
    # Deterministic scheduling duration. None means unknown: never bookable.
    booking_duration_minutes: int | None
    is_bookable: bool
    revision: int
    provides: frozenset[str] = field(default_factory=frozenset)
    # L1: ordered stages; empty means one active stage of the whole duration, as before.
    stages: tuple[StageSpec, ...] = ()


@dataclass(frozen=True, slots=True)
class AddOnSpec:
    id: UUID
    code: str
    name: str
    status: CatalogStatus
    price_cents: int
    currency: str
    duration_delta_minutes: int | None
    is_bookable: bool
    revision: int
    provides: frozenset[str] = field(default_factory=frozenset)
    requires: frozenset[str] = field(default_factory=frozenset)
    conflicts_with: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True, slots=True)
class QuoteLine:
    kind: Literal["variant", "add_on"]
    id: UUID
    code: str
    name: str
    price_cents: int
    duration_minutes: int
    revision: int


@dataclass(frozen=True, slots=True)
class Quote:
    currency: str
    total_cents: int
    booking_duration_minutes: int
    lines: tuple[QuoteLine, ...]
    # L1: the stages of the visit, with the add-ons' minutes; empty for a variant without stages.
    stages: tuple[StageSpec, ...] = ()

    def snapshot(self) -> dict[str, object]:
        """Immutable record stored with a booking (JSON-serialisable).

        Version 1 is unchanged for a variant without stages; version 2 adds its stages.
        """
        record = self._lines_snapshot()
        if self.stages:
            record["version"] = 2
            record["stages"] = [
                {"kind": s.kind, "minutes": s.minutes, "resources": list(s.resources)}
                for s in self.stages
            ]
        return record

    def _lines_snapshot(self) -> dict[str, object]:
        return {
            "version": 1,
            "currency": self.currency,
            "total_cents": self.total_cents,
            "booking_duration_minutes": self.booking_duration_minutes,
            "lines": [
                {
                    "kind": line.kind,
                    "id": str(line.id),
                    "code": line.code,
                    "name": line.name,
                    "price_cents": line.price_cents,
                    "duration_minutes": line.duration_minutes,
                    "revision": line.revision,
                }
                for line in self.lines
            ],
        }
