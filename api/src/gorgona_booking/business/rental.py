"""R1 (package R, RENT-01): rental item classes and units (ADR-0036).

A class is company-wide with a typed attribute set per revision; a unit is one physical item of a
class with an identifier unique in the business, a branch, a state and values checked against its
class. Each save replaces the head with the next revision and writes its attribute set or its values
insert-only. The database rechecks the revisions, the fixed code, class and identifier, the retired
state, every value's key and type and, at commit, the required values; it gates writes on
the module.
"""

import hashlib
import json
import re
from datetime import datetime
from typing import Annotated, Literal, Self
from uuid import UUID

from psycopg.errors import CheckViolation, ForeignKeyViolation, UniqueViolation
from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business import modules
from gorgona_booking.business.module_gate import RENTAL_MODULE, module_writes, require_module
from gorgona_booking.business.readiness_registry import at_least
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, InvalidReferenceError, NotFoundError
from gorgona_booking.tenancy.authorization import PermissionDeniedError

PAGE = 50
_NUMBER = re.compile(r"^-?(0|[1-9][0-9]{0,11})(\.[0-9]{1,6})?$")


class RentalNotReadyError(ConflictError):
    code = "MODULE_NOT_READY"


class RentalRevisionConflictError(ConflictError):
    code = "RENTAL_REVISION_CONFLICT"


class RentalCodeTakenError(ConflictError):
    code = "RENTAL_CODE_TAKEN"


class RentalCodeFixedError(ConflictError):
    code = "RENTAL_CODE_FIXED"


class RentalIdentifierTakenError(ConflictError):
    code = "RENTAL_IDENTIFIER_TAKEN"


class RentalUnitFixedError(ConflictError):
    code = "RENTAL_UNIT_FIXED"


class RentalUnitRetiredError(ConflictError):
    code = "RENTAL_UNIT_RETIRED"


class RentalValueInvalidError(DomainError):
    code = "RENTAL_VALUE_INVALID"


def _controls(value: str) -> bool:
    return any(ord(ch) < 32 or ord(ch) == 127 for ch in value)


def _one_line(value: str) -> str:
    if not value.strip() or _controls(value):
        raise ValueError("text without control characters")
    return value


OneLine = Annotated[str, AfterValidator(_one_line)]


class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)


class AttributeInput(Strict):
    key: str = Field(pattern=r"^[a-z][a-z0-9_]{0,31}$")
    label: Annotated[OneLine, Field(min_length=1, max_length=100)]
    type: Literal["text", "number", "boolean"]
    required: bool


class ClassInput(Strict):
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=2_147_483_647)
    code: str = Field(pattern=r"^[A-Z0-9][A-Z0-9_-]{0,31}$")
    name: Annotated[OneLine, Field(min_length=1, max_length=200)]
    meter_kind: Literal["none", "odometer", "hours"]
    attributes: list[AttributeInput] = Field(max_length=50)

    @model_validator(mode="after")
    def _unique_keys(self) -> Self:
        keys = [a.key for a in self.attributes]
        if len(keys) != len(set(keys)):
            raise ValueError("attribute keys are unique")
        return self


class UnitInput(Strict):
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=2_147_483_647)
    class_id: UUID
    identifier: Annotated[OneLine, Field(min_length=1, max_length=64)]
    location_id: UUID
    state: Literal["active", "retired"]
    values: dict[str, Annotated[str, Field(min_length=1, max_length=500)]] = Field(max_length=50)


class AttributeView(BaseModel):
    key: str
    label: str
    type: str
    required: bool


class ClassView(BaseModel):
    class_id: UUID
    revision: int
    code: str
    name: str
    meter_kind: str
    attributes: list[AttributeView]
    updated_at: datetime


class ClassList(BaseModel):
    items: list[ClassView]
    next_cursor: UUID | None = None


class UnitView(BaseModel):
    unit_id: UUID
    revision: int
    class_id: UUID
    identifier: str
    location_id: UUID
    state: str
    values: dict[str, str]
    updated_at: datetime


class UnitList(BaseModel):
    items: list[UnitView]
    next_cursor: UUID | None = None


async def require_rental(conn: RuntimeConnection, business: UUID) -> None:
    """Writes need an accepted module that this business enabled (ADR-0019, ADR-0036)."""
    current = modules.MODULES_BY_ID[RENTAL_MODULE]
    if not current.enableable or not at_least(current.readiness, modules.MINIMUM_READINESS):
        raise RentalNotReadyError("Rental has not been accepted", module_id=RENTAL_MODULE)
    await require_module(conn, business, RENTAL_MODULE)
    for dependency in current.depends_on:
        if modules.MODULES_BY_ID[dependency].kind == modules.ModuleKind.OPTIONAL:
            await require_module(conn, business, dependency)


def fingerprint(subject: str, body: BaseModel) -> str:
    return hashlib.sha256(
        json.dumps(
            {"subject": subject, "body": body.model_dump(mode="json")},
            sort_keys=True,
            separators=(",", ":"),
        ).encode()
    ).hexdigest()


async def caller_branch(conn: RuntimeConnection) -> UUID | None:
    """The caller's branch when it is branch-limited, else None."""
    row = await (await conn.execute("select gba.current_location_id()")).fetchone()
    return row[0] if row else None


async def _attributes(
    conn: RuntimeConnection, class_id: UUID, revision: int
) -> list[AttributeView]:
    rows = await (
        await conn.execute(
            "select key, label, type, required from gba.rental_class_attributes "
            "where class_id = %s and revision = %s order by position",
            (class_id, revision),
        )
    ).fetchall()
    return [AttributeView(key=r[0], label=r[1], type=r[2], required=r[3]) for r in rows]


async def load_class(conn: RuntimeConnection, class_id: UUID) -> ClassView | None:
    row = await (
        await conn.execute(
            "select revision, code, name, meter_kind, updated_at from gba.rental_classes "
            "where id = %s",
            (class_id,),
        )
    ).fetchone()
    if row is None:
        return None
    return ClassView(
        class_id=class_id,
        revision=row[0],
        code=row[1],
        name=row[2],
        meter_kind=row[3],
        attributes=await _attributes(conn, class_id, row[0]),
        updated_at=row[4],
    )


async def list_classes(conn: RuntimeConnection, after: UUID | None = None) -> ClassList:
    rows = await (
        await conn.execute(
            "select id from gba.rental_classes where %s::uuid is null or id > %s "
            "order by id limit %s",
            (after, after, PAGE + 1),
        )
    ).fetchall()
    views = [v for v in [await load_class(conn, r[0]) for r in rows[:PAGE]] if v is not None]
    more = len(rows) > PAGE and bool(views)
    return ClassList(items=views, next_cursor=views[-1].class_id if more else None)


async def save_class(
    conn: RuntimeConnection,
    business: UUID,
    class_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ClassInput,
) -> ClassView:
    """Replace a class whole with its expected revision and its full attribute set (decision 1)."""
    await require_rental(conn, business)
    if await caller_branch(conn) is not None:
        raise PermissionDeniedError("Classes are company-wide; a branch member does not write them")
    scope = IdempotencyScope(business, actor, "rental.class", key)
    request = fingerprint(str(class_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await load_class(conn, class_id)
        if view is None:
            raise NotFoundError("Class not found", class_id=str(class_id))
        return view
    current = await (
        await conn.execute(
            "select revision, code from gba.rental_classes where id = %s for update", (class_id,)
        )
    ).fetchone()
    found = 0 if current is None else int(current[0])
    if found != body.expected_revision:
        raise RentalRevisionConflictError(
            "The class changed since it was read; reload it", revision=found
        )
    if current is not None and current[1] != body.code:
        raise RentalCodeFixedError("A class keeps its code", code=current[1])
    revision = found + 1
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            if current is None:
                await conn.execute(
                    "insert into gba.rental_classes (tenant_id, id, code, name, meter_kind, "
                    "revision, created_by) values (%s, %s, %s, %s, %s, 1, %s)",
                    (business, class_id, body.code, body.name, body.meter_kind, user_id),
                )
            else:
                await conn.execute(
                    "update gba.rental_classes set name = %s, meter_kind = %s, "
                    "revision = revision + 1, updated_at = now() where id = %s",
                    (body.name, body.meter_kind, class_id),
                )
            for position, attribute in enumerate(body.attributes, start=1):
                await conn.execute(
                    "insert into gba.rental_class_attributes (tenant_id, class_id, revision, "
                    "position, key, label, type, required) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        class_id,
                        revision,
                        position,
                        attribute.key,
                        attribute.label,
                        attribute.type,
                        attribute.required,
                    ),
                )
    except UniqueViolation as exc:
        raise RentalCodeTakenError("Another class has this code") from exc
    view = await load_class(conn, class_id)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"class_id": str(class_id)})
    return view


async def load_unit(conn: RuntimeConnection, unit_id: UUID) -> UnitView | None:
    row = await (
        await conn.execute(
            "select revision, class_id, identifier, location_id, state, updated_at "
            "from gba.rental_units where id = %s",
            (unit_id,),
        )
    ).fetchone()
    if row is None:
        return None
    values = await (
        await conn.execute(
            "select key, value from gba.rental_unit_values where unit_id = %s and revision = %s "
            "order by key",
            (unit_id, row[0]),
        )
    ).fetchall()
    return UnitView(
        unit_id=unit_id,
        revision=row[0],
        class_id=row[1],
        identifier=row[2],
        location_id=row[3],
        state=row[4],
        values={str(k): str(v) for k, v in values},
        updated_at=row[5],
    )


async def list_units(
    conn: RuntimeConnection, after: UUID | None = None, class_id: UUID | None = None
) -> UnitList:
    rows = await (
        await conn.execute(
            "select id from gba.rental_units where (%s::uuid is null or id > %s) "
            "and (%s::uuid is null or class_id = %s) order by id limit %s",
            (after, after, class_id, class_id, PAGE + 1),
        )
    ).fetchall()
    views = [v for v in [await load_unit(conn, r[0]) for r in rows[:PAGE]] if v is not None]
    more = len(rows) > PAGE and bool(views)
    return UnitList(items=views, next_cursor=views[-1].unit_id if more else None)


def _check_values(attributes: list[AttributeView], values: dict[str, str]) -> None:
    """Every value fits an attribute of the class; every required attribute has one (decision 2)."""
    kinds = {a.key: a.type for a in attributes}
    for key, value in values.items():
        kind = kinds.get(key)
        if (
            kind is None
            or _controls(value)
            or (kind == "number" and not _NUMBER.match(value))
            or (kind == "boolean" and value not in ("true", "false"))
            or (kind == "text" and not value.strip())
        ):
            raise RentalValueInvalidError("A value does not fit the class", key=key)
    missing = [a.key for a in attributes if a.required and a.key not in values]
    if missing:
        raise RentalValueInvalidError("A required value is missing", key=missing[0])


async def save_unit(
    conn: RuntimeConnection,
    business: UUID,
    unit_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: UnitInput,
) -> UnitView:
    """Replace a unit whole with its expected revision and its values (decision 2)."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.unit", key)
    request = fingerprint(str(unit_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await load_unit(conn, unit_id)
        if view is None:
            raise NotFoundError("Unit not found", unit_id=str(unit_id))
        return view
    branch = await caller_branch(conn)
    known = await (
        await conn.execute("select 1 from gba.locations where id = %s", (body.location_id,))
    ).fetchone()
    if known is None or (branch is not None and branch != body.location_id):
        raise InvalidReferenceError("Unknown branch", field="location_id")
    klass = await load_class(conn, body.class_id)
    if klass is None:
        raise InvalidReferenceError("Unknown class", field="class_id")
    current = await (
        await conn.execute(
            "select revision, class_id, identifier, state from gba.rental_units "
            "where id = %s for update",
            (unit_id,),
        )
    ).fetchone()
    found = 0 if current is None else int(current[0])
    if found != body.expected_revision:
        raise RentalRevisionConflictError(
            "The unit changed since it was read; reload it", revision=found
        )
    if current is not None and current[3] == "retired":
        raise RentalUnitRetiredError("A retired unit takes no new revision")
    if current is not None and (current[1] != body.class_id or current[2] != body.identifier):
        raise RentalUnitFixedError("A unit keeps its class and identifier")
    _check_values(klass.attributes, body.values)
    revision = found + 1
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            if current is None:
                # R3a: every unit has its own occupancy resource in its branch.
                resource = await (
                    await conn.execute(
                        "insert into gba.resources (tenant_id, location_id, kind, display_name, "
                        "is_active) values (%s, %s, 'rental_unit', %s, %s) returning id",
                        (business, body.location_id, body.identifier, body.state == "active"),
                    )
                ).fetchone()
                assert resource is not None  # noqa: S101 - returning id
                await conn.execute(
                    "insert into gba.rental_units (tenant_id, id, class_id, identifier, "
                    "location_id, state, revision, created_by, resource_id) "
                    "values (%s, %s, %s, %s, %s, %s, 1, %s, %s)",
                    (
                        business,
                        unit_id,
                        body.class_id,
                        body.identifier,
                        body.location_id,
                        body.state,
                        user_id,
                        resource[0],
                    ),
                )
            else:
                await conn.execute(
                    "update gba.rental_units set location_id = %s, state = %s, "
                    "revision = revision + 1, updated_at = now() where id = %s",
                    (body.location_id, body.state, unit_id),
                )
                await conn.execute(
                    "update gba.resources r set location_id = %s, is_active = %s "
                    "from gba.rental_units u where u.id = %s and r.tenant_id = u.tenant_id "
                    "and r.id = u.resource_id",
                    (body.location_id, body.state == "active", unit_id),
                )
            for name, value in sorted(body.values.items()):
                await conn.execute(
                    "insert into gba.rental_unit_values (tenant_id, unit_id, revision, key, "
                    "value) values (%s, %s, %s, %s, %s)",
                    (business, unit_id, revision, name, value),
                )
            # The required values are checked at commit; check them now so a refusal is a 422.
            await conn.execute("set constraints gba.rental_units_required_values immediate")
    except UniqueViolation as exc:
        raise RentalIdentifierTakenError("Another unit has this identifier") from exc
    except ForeignKeyViolation as exc:
        raise InvalidReferenceError("Unknown reference", field="class_id") from exc
    except CheckViolation as exc:
        name = exc.diag.constraint_name or ""
        if name == "rental_units_retired_check":
            raise RentalUnitRetiredError("A retired unit takes no new revision") from exc
        if name == "rental_units_revision_sequence_check":
            raise RentalUnitFixedError("A unit keeps its class and identifier") from exc
        if name.startswith("rental_unit_values_"):
            raise RentalValueInvalidError("A value does not fit the class") from exc
        raise
    view = await load_unit(conn, unit_id)
    assert view is not None  # noqa: S101 - saved above
    await idempotency.complete(conn, scope, 200, {"unit_id": str(unit_id)})
    return view
