"""REST-01 Slice 1 (ADR-0037): dining areas, tables and independent table reservations."""

import re
from datetime import timedelta
from typing import Literal, Self
from uuid import UUID, uuid7

from psycopg import errors
from psycopg.rows import class_row
from pydantic import AwareDatetime, Field, StrictInt, field_validator, model_validator

from gorgona_booking.booking import repository as repo
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import SlotConflictError
from gorgona_booking.business import commands, modules
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import (
    ConflictError,
    InvalidReferenceError,
    NotFoundError,
)
from gorgona_booking.tenancy.authorization import PermissionDeniedError

RESTAURANT_MODULE = "restaurant"
ServiceStyle = Literal["dining", "bar", "patio", "private"]
ReservationStatus = Literal["booked", "seated", "completed", "cancelled", "no_show"]
ReservationAction = Literal["seat", "complete", "cancel", "no_show"]

_MAX_REVISION = 2_147_483_647
_MAX_RESERVATION = timedelta(hours=24)
_SINGLE_LINE_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_MULTILINE_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

_ACTION_TARGET: dict[ReservationAction, ReservationStatus] = {
    "seat": "seated",
    "complete": "completed",
    "cancel": "cancelled",
    "no_show": "no_show",
}
_ALLOWED_TRANSITIONS: dict[ReservationStatus, frozenset[ReservationStatus]] = {
    "booked": frozenset({"seated", "cancelled", "no_show"}),
    "seated": frozenset({"completed", "cancelled"}),
    "completed": frozenset(),
    "cancelled": frozenset(),
    "no_show": frozenset(),
}


class RestaurantNotReadyError(ConflictError):
    code = "RESTAURANT_NOT_READY"


class RestaurantRevisionError(ConflictError):
    code = "RESTAURANT_REVISION_CONFLICT"


class RestaurantStateError(ConflictError):
    code = "RESTAURANT_STATE_INVALID"


def _clean_single_line(value: str, max_len: int) -> str:
    if _SINGLE_LINE_CTRL.search(value):
        raise ValueError("Control characters are not allowed")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > max_len:
        raise ValueError(f"Enter between 1 and {max_len} characters")
    return cleaned


def _clean_multiline(value: str, max_len: int) -> str:
    if _MULTILINE_CTRL.search(value):
        raise ValueError("Control characters are not allowed")
    cleaned = value.strip()
    if not cleaned or len(cleaned) > max_len:
        raise ValueError(f"Enter between 1 and {max_len} characters")
    return cleaned


class AreaInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION - 1)
    location_id: UUID
    name: str
    service_style: ServiceStyle
    is_active: bool = True

    @field_validator("name")
    @classmethod
    def valid_name(cls, value: str) -> str:
        return _clean_single_line(value, 120)


class AreaView(Strict):
    schema_version: Literal[1] = 1
    area_id: UUID
    location_id: UUID
    name: str
    service_style: ServiceStyle
    revision: int
    is_active: bool
    recorded_by: UUID
    recorded_at: AwareDatetime


class AreaList(Strict):
    schema_version: Literal[1] = 1
    items: list[AreaView]
    next_after: UUID | None = None


class TableInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION - 1)
    location_id: UUID
    area_id: UUID
    code: str
    min_covers: StrictInt = Field(ge=1, le=100)
    max_covers: StrictInt = Field(ge=1, le=100)
    is_active: bool = True

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return _clean_single_line(value, 32)

    @model_validator(mode="after")
    def valid_covers(self) -> Self:
        if self.max_covers < self.min_covers:
            raise ValueError("Maximum covers must be at least minimum covers")
        return self


class TableView(Strict):
    schema_version: Literal[1] = 1
    table_id: UUID
    location_id: UUID
    area_id: UUID
    resource_id: UUID
    code: str
    min_covers: int
    max_covers: int
    revision: int
    is_active: bool
    recorded_by: UUID
    recorded_at: AwareDatetime


class TableList(Strict):
    schema_version: Literal[1] = 1
    items: list[TableView]
    next_after: UUID | None = None


class ReservationInput(Versioned):
    table_id: UUID
    guest_counterparty_id: UUID | None = None
    guest_name: str
    party_size: StrictInt = Field(ge=1, le=100)
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    note: str | None = None

    @field_validator("guest_name")
    @classmethod
    def valid_guest_name(cls, value: str) -> str:
        return _clean_single_line(value, 120)

    @field_validator("note")
    @classmethod
    def valid_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_multiline(value, 1000)

    @model_validator(mode="after")
    def valid_interval(self) -> Self:
        if self.ends_at <= self.starts_at:
            raise ValueError("Reservation end must be after start")
        if self.ends_at - self.starts_at > _MAX_RESERVATION:
            raise ValueError("Reservation duration cannot exceed 24 hours")
        return self


class ReservationView(Strict):
    schema_version: Literal[1] = 1
    reservation_id: UUID
    location_id: UUID
    table_id: UUID
    table_resource_id: UUID
    guest_counterparty_id: UUID | None
    guest_name: str
    party_size: int
    starts_at: AwareDatetime
    ends_at: AwareDatetime
    note: str | None
    status: ReservationStatus
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class ReservationList(Strict):
    schema_version: Literal[1] = 1
    items: list[ReservationView]
    next_after: UUID | None = None


class ReservationEventInput(Versioned):
    expected_revision: StrictInt = Field(ge=1, le=_MAX_REVISION - 1)
    action: ReservationAction
    note: str | None = None

    @field_validator("note")
    @classmethod
    def valid_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_multiline(value, 1000)


class ReservationEventView(Strict):
    schema_version: Literal[1] = 1
    reservation_id: UUID
    revision: int
    action: ReservationAction
    note: str | None
    recorded_by: UUID
    recorded_at: AwareDatetime


class ReservationEventList(Strict):
    schema_version: Literal[1] = 1
    items: list[ReservationEventView]


class _AreaReceipt(Strict):
    area_id: UUID


class _TableReceipt(Strict):
    table_id: UUID


class _ReservationReceipt(Strict):
    reservation_id: UUID


class _ReservationEventReceipt(Strict):
    reservation_id: UUID
    revision: int


_SELECT_AREA = """
select id as area_id, location_id, name, service_style, revision, is_active,
       recorded_by, recorded_at
from gba.restaurant_areas
where tenant_id = %s and id = %s
"""

_SELECT_TABLE = """
select id as table_id, location_id, area_id, resource_id, code, min_covers, max_covers,
       revision, is_active, recorded_by, recorded_at
from gba.restaurant_tables
where tenant_id = %s and id = %s
"""

_SELECT_RESERVATION = """
select id as reservation_id, location_id, table_id, table_resource_id,
       guest_counterparty_id, guest_name, party_size, starts_at, ends_at,
       note, status, revision, recorded_by, recorded_at
from gba.restaurant_table_reservations
where tenant_id = %s and id = %s
"""


def _check_ready() -> None:
    if not modules.MODULES_BY_ID[RESTAURANT_MODULE].enableable:
        raise RestaurantNotReadyError(
            "The restaurant module is not ready", details={"module_id": RESTAURANT_MODULE}
        )


async def _ensure_location_exists(
    conn: RuntimeConnection, business: UUID, location_id: UUID
) -> None:
    found = await (
        await conn.execute(
            "select 1 from gba.locations where tenant_id = %s and id = %s",
            (business, location_id),
        )
    ).fetchone()
    if found is None:
        raise InvalidReferenceError("Unknown branch", field="location_id")


async def list_areas(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
    after: UUID | None = None,
    limit: int = 50,
) -> AreaList:
    async with conn.cursor(row_factory=class_row(AreaView)) as cur:
        await cur.execute(
            "select id as area_id, location_id, name, service_style, revision, is_active, "
            "recorded_by, recorded_at from gba.restaurant_areas "
            "where tenant_id = %s "
            "and (%s::uuid is null or location_id = %s::uuid) "
            "and (%s::uuid is null or id > %s::uuid) "
            "order by id limit %s",
            (business, location_id, location_id, after, after, limit + 1),
        )
        rows = await cur.fetchall()
    has_more = len(rows) > limit
    items = rows[:limit]
    return AreaList(items=items, next_after=items[-1].area_id if has_more else None)


async def get_area(conn: RuntimeConnection, business: UUID, area_id: UUID) -> AreaView:
    async with conn.cursor(row_factory=class_row(AreaView)) as cur:
        await cur.execute(_SELECT_AREA, (business, area_id))
        found = await cur.fetchone()
    if found is None:
        raise NotFoundError("Restaurant area not found")
    return found


async def save_area(
    conn: RuntimeConnection,
    business: UUID,
    area_id: UUID,
    *,
    location_scope: UUID | None,
    user_id: UUID,
    actor: str,
    key: str,
    body: AreaInput,
) -> AreaView:
    if location_scope is not None and body.location_id != location_scope:
        raise PermissionDeniedError("You can only manage dining areas in your assigned branch")
    scope = IdempotencyScope(business, actor, "restaurant.area.save", key)
    fingerprint = commands.fingerprint(
        {"area_id": str(area_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _AreaReceipt)
    if receipt is not None:
        return await get_area(conn, business, receipt.area_id)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)
    await _ensure_location_exists(conn, business, body.location_id)

    async with module_writes(RESTAURANT_MODULE):
        existing = await (
            await conn.execute(
                "select location_id, revision from gba.restaurant_areas "
                "where tenant_id = %s and id = %s for update",
                (business, area_id),
            )
        ).fetchone()
        if existing is None:
            if body.expected_revision != 0:
                raise RestaurantRevisionError(
                    "Restaurant area does not exist for this revision",
                    details={"revision": 0},
                )
            next_rev = 1
            await conn.execute(
                "insert into gba.restaurant_areas "
                "(tenant_id, id, location_id, name, service_style, "
                "revision, is_active, recorded_by) "
                "values (%s, %s, %s, %s, %s, 1, %s, %s)",
                (
                    business,
                    area_id,
                    body.location_id,
                    body.name,
                    body.service_style,
                    body.is_active,
                    user_id,
                ),
            )
        else:
            existing_loc, current_rev = existing
            if body.expected_revision != current_rev:
                raise RestaurantRevisionError(
                    "Restaurant area has changed", details={"revision": current_rev}
                )
            if existing_loc != body.location_id:
                raise InvalidReferenceError(
                    "A dining area cannot move to another branch", field="location_id"
                )
            next_rev = current_rev + 1
            await conn.execute(
                "update gba.restaurant_areas "
                "set name = %s, service_style = %s, revision = %s, is_active = %s, "
                "recorded_by = %s, recorded_at = clock_timestamp() "
                "where tenant_id = %s and id = %s",
                (
                    body.name,
                    body.service_style,
                    next_rev,
                    body.is_active,
                    user_id,
                    business,
                    area_id,
                ),
            )
        await conn.execute(
            "insert into gba.restaurant_area_revisions "
            "(tenant_id, area_id, revision, location_id, name, "
            "service_style, is_active, recorded_by) "
            "values (%s, %s, %s, %s, %s, %s, %s, %s)",
            (
                business,
                area_id,
                next_rev,
                body.location_id,
                body.name,
                body.service_style,
                body.is_active,
                user_id,
            ),
        )

    await commands.audit(
        conn,
        business,
        actor,
        "restaurant.area_saved",
        "restaurant_area",
        str(area_id),
        {"location_id": str(body.location_id), "revision": next_rev},
    )
    await commands.complete(conn, scope, _AreaReceipt(area_id=area_id))
    return await get_area(conn, business, area_id)


async def list_tables(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
    area_id: UUID | None = None,
    after: UUID | None = None,
    limit: int = 50,
) -> TableList:
    async with conn.cursor(row_factory=class_row(TableView)) as cur:
        await cur.execute(
            "select id as table_id, location_id, area_id, resource_id, code, min_covers, "
            "max_covers, revision, is_active, recorded_by, recorded_at from gba.restaurant_tables "
            "where tenant_id = %s "
            "and (%s::uuid is null or location_id = %s::uuid) "
            "and (%s::uuid is null or area_id = %s::uuid) "
            "and (%s::uuid is null or id > %s::uuid) "
            "order by id limit %s",
            (business, location_id, location_id, area_id, area_id, after, after, limit + 1),
        )
        rows = await cur.fetchall()
    has_more = len(rows) > limit
    items = rows[:limit]
    return TableList(items=items, next_after=items[-1].table_id if has_more else None)


async def get_table(conn: RuntimeConnection, business: UUID, table_id: UUID) -> TableView:
    async with conn.cursor(row_factory=class_row(TableView)) as cur:
        await cur.execute(_SELECT_TABLE, (business, table_id))
        found = await cur.fetchone()
    if found is None:
        raise NotFoundError("Restaurant table not found")
    return found


async def save_table(
    conn: RuntimeConnection,
    business: UUID,
    table_id: UUID,
    *,
    location_scope: UUID | None,
    user_id: UUID,
    actor: str,
    key: str,
    body: TableInput,
) -> TableView:
    if location_scope is not None and body.location_id != location_scope:
        raise PermissionDeniedError("You can only manage tables in your assigned branch")
    scope = IdempotencyScope(business, actor, "restaurant.table.save", key)
    fingerprint = commands.fingerprint(
        {"table_id": str(table_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _TableReceipt)
    if receipt is not None:
        return await get_table(conn, business, receipt.table_id)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)
    await _ensure_location_exists(conn, business, body.location_id)

    area = await (
        await conn.execute(
            "select 1 from gba.restaurant_areas "
            "where tenant_id = %s and id = %s and location_id = %s",
            (business, body.area_id, body.location_id),
        )
    ).fetchone()
    if area is None:
        raise InvalidReferenceError("Unknown dining area in this branch", field="area_id")

    try:
        async with module_writes(RESTAURANT_MODULE):
            existing = await (
                await conn.execute(
                    "select location_id, revision from gba.restaurant_tables "
                    "where tenant_id = %s and id = %s for update",
                    (business, table_id),
                )
            ).fetchone()
            if existing is None:
                if body.expected_revision != 0:
                    raise RestaurantRevisionError(
                        "Restaurant table does not exist for this revision",
                        details={"revision": 0},
                    )
                next_rev = 1
                resource_id = uuid7()
                await conn.execute(
                    "insert into gba.resources (tenant_id, id, location_id, kind, display_name) "
                    "values (%s, %s, %s, 'restaurant_table', %s)",
                    (business, resource_id, body.location_id, f"Table {body.code}"),
                )
                await conn.execute(
                    "insert into gba.restaurant_tables "
                    "(tenant_id, id, location_id, area_id, resource_id, code, min_covers, "
                    "max_covers, revision, is_active, recorded_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)",
                    (
                        business,
                        table_id,
                        body.location_id,
                        body.area_id,
                        resource_id,
                        body.code,
                        body.min_covers,
                        body.max_covers,
                        body.is_active,
                        user_id,
                    ),
                )
            else:
                existing_loc, current_rev = existing
                if body.expected_revision != current_rev:
                    raise RestaurantRevisionError(
                        "Restaurant table has changed", details={"revision": current_rev}
                    )
                if existing_loc != body.location_id:
                    raise InvalidReferenceError(
                        "A table cannot move to another branch", field="location_id"
                    )
                next_rev = current_rev + 1
                await conn.execute(
                    "update gba.restaurant_tables "
                    "set area_id = %s, code = %s, min_covers = %s, max_covers = %s, "
                    "revision = %s, is_active = %s, recorded_by = %s, "
                    "recorded_at = clock_timestamp() "
                    "where tenant_id = %s and id = %s",
                    (
                        body.area_id,
                        body.code,
                        body.min_covers,
                        body.max_covers,
                        next_rev,
                        body.is_active,
                        user_id,
                        business,
                        table_id,
                    ),
                )
    except errors.UniqueViolation as exc:
        if exc.diag.constraint_name == "restaurant_tables_tenant_id_location_id_code_key":
            raise ConflictError("A table with this code already exists in this branch") from exc
        raise

    await commands.audit(
        conn,
        business,
        actor,
        "restaurant.table_saved",
        "restaurant_table",
        str(table_id),
        {"location_id": str(body.location_id), "code": body.code, "revision": next_rev},
    )
    await commands.complete(conn, scope, _TableReceipt(table_id=table_id))
    return await get_table(conn, business, table_id)


async def list_reservations(
    conn: RuntimeConnection,
    business: UUID,
    *,
    location_id: UUID | None = None,
    table_id: UUID | None = None,
    status: ReservationStatus | None = None,
    after: UUID | None = None,
    limit: int = 50,
) -> ReservationList:
    async with conn.cursor(row_factory=class_row(ReservationView)) as cur:
        await cur.execute(
            "select id as reservation_id, location_id, table_id, table_resource_id, "
            "guest_counterparty_id, guest_name, party_size, starts_at, ends_at, "
            "note, status, revision, recorded_by, recorded_at "
            "from gba.restaurant_table_reservations where tenant_id = %s "
            "and (%s::uuid is null or location_id = %s::uuid) "
            "and (%s::uuid is null or table_id = %s::uuid) "
            "and (%s::text is null or status = %s::text) "
            "and (%s::uuid is null or id > %s::uuid) "
            "order by id limit %s",
            (
                business,
                location_id,
                location_id,
                table_id,
                table_id,
                status,
                status,
                after,
                after,
                limit + 1,
            ),
        )
        rows = await cur.fetchall()
    has_more = len(rows) > limit
    items = rows[:limit]
    return ReservationList(items=items, next_after=items[-1].reservation_id if has_more else None)


async def get_reservation(
    conn: RuntimeConnection, business: UUID, reservation_id: UUID
) -> ReservationView:
    async with conn.cursor(row_factory=class_row(ReservationView)) as cur:
        await cur.execute(_SELECT_RESERVATION, (business, reservation_id))
        found = await cur.fetchone()
    if found is None:
        raise NotFoundError("Table reservation not found")
    return found


async def create_reservation(
    conn: RuntimeConnection,
    business: UUID,
    reservation_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ReservationInput,
) -> ReservationView:
    scope = IdempotencyScope(business, actor, "restaurant.reservation.create", key)
    fingerprint = commands.fingerprint(
        {"reservation_id": str(reservation_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _ReservationReceipt)
    if receipt is not None:
        return await get_reservation(conn, business, receipt.reservation_id)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)

    tbl = await (
        await conn.execute(
            "select location_id, resource_id, min_covers, max_covers, is_active "
            "from gba.restaurant_tables where tenant_id = %s and id = %s for share",
            (business, body.table_id),
        )
    ).fetchone()
    if tbl is None:
        raise NotFoundError("Restaurant table not found")
    location_id, resource_id, min_covers, max_covers, is_active = tbl
    if not is_active:
        raise RestaurantStateError("This table is inactive and cannot be reserved")
    if body.party_size < min_covers or body.party_size > max_covers:
        raise InvalidReferenceError(
            f"Party size must be between {min_covers} and {max_covers} for this table",
            field="party_size",
        )

    try:
        async with module_writes(RESTAURANT_MODULE):
            await repo.lock_resource_schedule(conn, business, resource_id)
            await conn.execute(
                "insert into gba.restaurant_table_reservations "
                "(tenant_id, id, location_id, table_id, table_resource_id, guest_counterparty_id, "
                "guest_name, party_size, starts_at, ends_at, note, status, revision, recorded_by) "
                "values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'booked', 1, %s)",
                (
                    business,
                    reservation_id,
                    location_id,
                    body.table_id,
                    resource_id,
                    body.guest_counterparty_id,
                    body.guest_name,
                    body.party_size,
                    body.starts_at,
                    body.ends_at,
                    body.note,
                    user_id,
                ),
            )
            await conn.execute(
                "insert into gba.resource_allocations "
                "(tenant_id, resource_id, source_kind, source_id, during, state) "
                "values (%s, %s, 'restaurant_reservation', %s, "
                "tstzrange(%s, %s, '[)'), 'confirmed')",
                (business, resource_id, reservation_id, body.starts_at, body.ends_at),
            )
    except errors.ExclusionViolation as exc:
        if repo.is_slot_conflict(exc):
            raise SlotConflictError("This table is already reserved in this interval") from exc
        raise
    except errors.UniqueViolation as exc:
        if exc.diag.constraint_name == "restaurant_table_reservations_pkey":
            raise ConflictError("This table reservation already exists") from exc
        raise
    except errors.ForeignKeyViolation as exc:
        if exc.diag.constraint_name == "restaurant_table_reservations_guest_fk":
            raise InvalidReferenceError(
                "Unknown guest counterparty", field="guest_counterparty_id"
            ) from exc
        raise

    await commands.audit(
        conn,
        business,
        actor,
        "restaurant.reservation_created",
        "restaurant_table_reservation",
        str(reservation_id),
        {
            "location_id": str(location_id),
            "table_id": str(body.table_id),
            "party_size": body.party_size,
        },
    )
    await commands.complete(conn, scope, _ReservationReceipt(reservation_id=reservation_id))
    return await get_reservation(conn, business, reservation_id)


async def list_reservation_events(
    conn: RuntimeConnection, business: UUID, reservation_id: UUID
) -> ReservationEventList:
    await get_reservation(conn, business, reservation_id)
    async with conn.cursor(row_factory=class_row(ReservationEventView)) as cur:
        await cur.execute(
            "select reservation_id, revision, action, note, recorded_by, recorded_at "
            "from gba.restaurant_table_reservation_events "
            "where tenant_id = %s and reservation_id = %s order by revision",
            (business, reservation_id),
        )
        items = await cur.fetchall()
    return ReservationEventList(items=items)


async def record_reservation_event(
    conn: RuntimeConnection,
    business: UUID,
    reservation_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ReservationEventInput,
) -> ReservationView:
    scope = IdempotencyScope(business, actor, "restaurant.reservation.event", key)
    fingerprint = commands.fingerprint(
        {"reservation_id": str(reservation_id), "body": body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _ReservationEventReceipt)
    if receipt is not None:
        return await get_reservation(conn, business, receipt.reservation_id)
    _check_ready()
    await require_module(conn, business, RESTAURANT_MODULE)

    async with module_writes(RESTAURANT_MODULE):
        row = await (
            await conn.execute(
                "select location_id, status, revision from gba.restaurant_table_reservations "
                "where tenant_id = %s and id = %s for update",
                (business, reservation_id),
            )
        ).fetchone()
        if row is None:
            raise NotFoundError("Table reservation not found")
        location_id, current_status, current_rev = row
        if current_rev != body.expected_revision:
            raise RestaurantRevisionError(
                "Table reservation has changed", details={"revision": current_rev}
            )
        target = _ACTION_TARGET[body.action]
        if target not in _ALLOWED_TRANSITIONS[current_status]:
            raise RestaurantStateError(
                f"Cannot {body.action} a reservation that is {current_status}"
            )
        next_rev = current_rev + 1
        await conn.execute(
            "insert into gba.restaurant_table_reservation_events "
            "(tenant_id, reservation_id, revision, location_id, action, note, recorded_by) "
            "values (%s, %s, %s, %s, %s, %s, %s)",
            (business, reservation_id, next_rev, location_id, body.action, body.note, user_id),
        )
        await conn.execute(
            "update gba.restaurant_table_reservations "
            "set status = %s, revision = %s, recorded_by = %s, recorded_at = clock_timestamp() "
            "where tenant_id = %s and id = %s",
            (target, next_rev, user_id, business, reservation_id),
        )

    await commands.audit(
        conn,
        business,
        actor,
        f"restaurant.reservation_{body.action}",
        "restaurant_table_reservation",
        str(reservation_id),
        {"location_id": str(location_id), "revision": next_rev, "status": target},
    )
    await commands.complete(
        conn,
        scope,
        _ReservationEventReceipt(reservation_id=reservation_id, revision=next_rev),
    )
    return await get_reservation(conn, business, reservation_id)
