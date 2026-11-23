"""SPECIAL-01 (ADR-0042): Typed domain workflows for Education cohorts & Fitness memberships,
Hospitality rooms & stays with housekeeping states, and Events & ticket capacity control.
"""

from datetime import date
from typing import Any, Literal
from uuid import UUID

from psycopg import errors
from pydantic import AwareDatetime, Field, field_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, modules
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.ledger_contracts import CURRENCY_PATTERN
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.readiness_registry import at_least
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError

SPECIAL_VENUES_MODULE = "hospitality_events"

ProgramKind = Literal["education_cohort", "fitness_membership", "club_pass"]
EnrollmentStatus = Literal["active", "completed", "cancelled"]
HousekeepingStatus = Literal["clean", "occupied", "dirty", "maintenance"]
StayStatus = Literal["reserved", "checked_in", "checked_out", "cancelled"]
EventStatus = Literal["scheduled", "completed", "cancelled"]
TicketStatus = Literal["issued", "checked_in", "cancelled"]


class SpecialVenuesNotReadyError(ConflictError):
    code = "MODULE_NOT_READY"


class SpecialVenuesStateError(ConflictError):
    code = "SPECIAL_STATE_INVALID"


class SpecialVenuesCapacityError(ConflictError):
    code = "SPECIAL_CAPACITY_EXCEEDED"


def _check_ready() -> None:
    mod = modules.MODULES_BY_ID[SPECIAL_VENUES_MODULE]
    if not mod.enableable or not at_least(mod.readiness, modules.MINIMUM_READINESS):
        raise SpecialVenuesNotReadyError(
            "Hospitality/events/education module is not enabled for production writes",
            module_id=SPECIAL_VENUES_MODULE,
        )


def _clean_code(value: str) -> str:
    clean = value.strip().upper()
    if len(clean) < 2 or len(clean) > 64:
        raise ValueError("Code must be 2..64 characters")
    if not clean[0].isalnum() or not all(c.isalnum() or c in "_-" for c in clean):
        raise ValueError("Code must use uppercase alphanumeric, _ or -")
    return clean


def _clean_line(value: str, max_len: int) -> str:
    clean = value.strip()
    if not clean or len(clean) > max_len or "\n" in clean or "\r" in clean:
        raise ValueError(f"Expected non-empty single-line text up to {max_len} chars")
    return clean


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------


class ProgramInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    code: str
    title: str
    program_kind: ProgramKind
    capacity: int = Field(ge=1, le=100_000)
    included_sessions: int = Field(default=1, ge=1, le=10_000)
    price_minor: int = Field(default=0, ge=0, le=999_999_999_999_999)
    currency: str = Field(pattern=CURRENCY_PATTERN)

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return _clean_code(value)

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _clean_line(value, 200)


class ProgramView(Strict):
    schema_version: Literal[1] = 1
    program_id: UUID
    location_id: UUID
    code: str
    title: str
    program_kind: ProgramKind
    capacity: int
    enrolled_count: int
    included_sessions: int
    price_minor: int
    currency: str
    is_active: bool
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class ProgramList(Strict):
    schema_version: Literal[1] = 1
    items: list[ProgramView]


class EnrollmentInput(Versioned):
    location_id: UUID
    program_id: UUID
    participant_counterparty_id: UUID


class EnrollmentSessionUseInput(Versioned):
    sessions_delta: int = Field(default=1, ge=1, le=100)
    result_grade: str | None = None


class EnrollmentView(Strict):
    schema_version: Literal[1] = 1
    enrollment_id: UUID
    location_id: UUID
    program_id: UUID
    participant_counterparty_id: UUID
    status: EnrollmentStatus
    sessions_used: int
    sessions_total: int
    result_grade: str | None
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class RoomInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    room_number: str
    room_type: str
    max_guests: int = Field(default=2, ge=1, le=50)
    nightly_rate_minor: int = Field(default=0, ge=0, le=999_999_999_999_999)
    currency: str = Field(pattern=CURRENCY_PATTERN)
    housekeeping_status: HousekeepingStatus = "clean"

    @field_validator("room_number")
    @classmethod
    def valid_num(cls, value: str) -> str:
        return _clean_line(value, 32)

    @field_validator("room_type")
    @classmethod
    def valid_type(cls, value: str) -> str:
        return _clean_line(value, 80)


class RoomView(Strict):
    schema_version: Literal[1] = 1
    room_id: UUID
    location_id: UUID
    room_number: str
    room_type: str
    max_guests: int
    nightly_rate_minor: int
    currency: str
    housekeeping_status: HousekeepingStatus
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class StayInput(Versioned):
    location_id: UUID
    room_id: UUID
    guest_counterparty_id: UUID
    check_in_date: date
    check_out_date: date
    guest_count: int = Field(default=1, ge=1, le=50)


class StayTransitionInput(Versioned):
    action: Literal["check_in", "check_out", "cancel"]


class StayView(Strict):
    schema_version: Literal[1] = 1
    stay_id: UUID
    location_id: UUID
    room_id: UUID
    guest_counterparty_id: UUID
    check_in_date: date
    check_out_date: date
    guest_count: int
    status: StayStatus
    checked_in_at: AwareDatetime | None
    checked_out_at: AwareDatetime | None
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class EventInput(Versioned):
    expected_revision: int = Field(ge=0, le=1_000_000)
    location_id: UUID
    code: str
    title: str
    event_date: date
    capacity: int = Field(ge=1, le=1_000_000)
    ticket_price_minor: int = Field(default=0, ge=0, le=999_999_999_999_999)
    currency: str = Field(pattern=CURRENCY_PATTERN)

    @field_validator("code")
    @classmethod
    def valid_code(cls, value: str) -> str:
        return _clean_code(value)

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _clean_line(value, 200)


class EventView(Strict):
    schema_version: Literal[1] = 1
    event_id: UUID
    location_id: UUID
    code: str
    title: str
    event_date: date
    capacity: int
    tickets_sold: int
    ticket_price_minor: int
    currency: str
    status: EventStatus
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


class TicketInput(Versioned):
    location_id: UUID
    event_id: UUID
    attendee_counterparty_id: UUID
    ticket_code: str
    quantity: int = Field(default=1, ge=1, le=100)

    @field_validator("ticket_code")
    @classmethod
    def valid_tcode(cls, value: str) -> str:
        return _clean_line(value, 64)


class TicketTransitionInput(Versioned):
    action: Literal["check_in", "cancel"]


class TicketView(Strict):
    schema_version: Literal[1] = 1
    ticket_id: UUID
    location_id: UUID
    event_id: UUID
    attendee_counterparty_id: UUID
    ticket_code: str
    quantity: int
    status: TicketStatus
    checked_in_at: AwareDatetime | None
    revision: int
    recorded_by: UUID
    recorded_at: AwareDatetime


# ---------------------------------------------------------------------------
# Row Mappers
# ---------------------------------------------------------------------------


def _program_view(r: tuple[Any, ...]) -> ProgramView:
    return ProgramView(
        program_id=r[0],
        location_id=r[1],
        code=str(r[2]),
        title=str(r[3]),
        program_kind=r[4],
        capacity=int(r[5]),
        enrolled_count=int(r[6]),
        included_sessions=int(r[7]),
        price_minor=int(r[8]),
        currency=str(r[9]),
        is_active=bool(r[10]),
        revision=int(r[11]),
        recorded_by=r[12],
        recorded_at=r[13],
    )


def _enrollment_view(r: tuple[Any, ...]) -> EnrollmentView:
    return EnrollmentView(
        enrollment_id=r[0],
        location_id=r[1],
        program_id=r[2],
        participant_counterparty_id=r[3],
        status=r[4],
        sessions_used=int(r[5]),
        sessions_total=int(r[6]),
        result_grade=r[7],
        revision=int(r[8]),
        recorded_by=r[9],
        recorded_at=r[10],
    )


def _room_view(r: tuple[Any, ...]) -> RoomView:
    return RoomView(
        room_id=r[0],
        location_id=r[1],
        room_number=str(r[2]),
        room_type=str(r[3]),
        max_guests=int(r[4]),
        nightly_rate_minor=int(r[5]),
        currency=str(r[6]),
        housekeeping_status=r[7],
        revision=int(r[8]),
        recorded_by=r[9],
        recorded_at=r[10],
    )


def _stay_view(r: tuple[Any, ...]) -> StayView:
    return StayView(
        stay_id=r[0],
        location_id=r[1],
        room_id=r[2],
        guest_counterparty_id=r[3],
        check_in_date=r[4],
        check_out_date=r[5],
        guest_count=int(r[6]),
        status=r[7],
        checked_in_at=r[8],
        checked_out_at=r[9],
        revision=int(r[10]),
        recorded_by=r[11],
        recorded_at=r[12],
    )


def _event_view(r: tuple[Any, ...]) -> EventView:
    return EventView(
        event_id=r[0],
        location_id=r[1],
        code=str(r[2]),
        title=str(r[3]),
        event_date=r[4],
        capacity=int(r[5]),
        tickets_sold=int(r[6]),
        ticket_price_minor=int(r[7]),
        currency=str(r[8]),
        status=r[9],
        revision=int(r[10]),
        recorded_by=r[11],
        recorded_at=r[12],
    )


def _ticket_view(r: tuple[Any, ...]) -> TicketView:
    return TicketView(
        ticket_id=r[0],
        location_id=r[1],
        event_id=r[2],
        attendee_counterparty_id=r[3],
        ticket_code=str(r[4]),
        quantity=int(r[5]),
        status=r[6],
        checked_in_at=r[7],
        revision=int(r[8]),
        recorded_by=r[9],
        recorded_at=r[10],
    )


# ---------------------------------------------------------------------------
# Education & Fitness
# ---------------------------------------------------------------------------


async def list_programs(conn: RuntimeConnection, business: UUID) -> ProgramList:
    rows = await (
        await conn.execute(
            "select id, location_id, code, title, program_kind, capacity, enrolled_count, "
            "included_sessions, price_minor, currency, is_active, revision, recorded_by, "
            "recorded_at from gba.special_programs where tenant_id = %s order by code",
            (business,),
        )
    ).fetchall()
    return ProgramList(items=[_program_view(r) for r in rows])


async def save_program(
    conn: RuntimeConnection,
    business: UUID,
    program_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ProgramInput,
) -> ProgramView:
    _check_ready()
    await require_module(conn, business, SPECIAL_VENUES_MODULE)
    scope = IdempotencyScope(business, actor, "special.program.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"program_id": str(program_id), **body.model_dump(mode="json")}),
        ProgramView,
    )
    if replay is not None:
        return replay

    async with module_writes(SPECIAL_VENUES_MODULE):
        existing = await (
            await conn.execute(
                "select revision, enrolled_count from gba.special_programs "
                "where tenant_id = %s and id = %s for update",
                (business, program_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise SpecialVenuesStateError("Program does not exist yet")
                await conn.execute(
                    "insert into gba.special_programs ("
                    "id, tenant_id, location_id, code, title, program_kind, capacity, "
                    "enrolled_count, included_sessions, price_minor, currency, revision, "
                    "recorded_by) values (%s, %s, %s, %s, %s, %s, %s, 0, %s, %s, %s, 1, %s)",
                    (
                        program_id,
                        business,
                        body.location_id,
                        body.code,
                        body.title,
                        body.program_kind,
                        body.capacity,
                        body.included_sessions,
                        body.price_minor,
                        body.currency,
                        user_id,
                    ),
                )
            else:
                if body.expected_revision != int(existing[0]):
                    raise SpecialVenuesStateError("Program revision mismatch")
                if body.capacity < int(existing[1]):
                    raise SpecialVenuesCapacityError("Capacity cannot be below enrolled count")
                await conn.execute(
                    "update gba.special_programs set code = %s, title = %s, capacity = %s, "
                    "included_sessions = %s, price_minor = %s, revision = revision + 1, "
                    "recorded_by = %s, recorded_at = now() where tenant_id = %s and id = %s",
                    (
                        body.code,
                        body.title,
                        body.capacity,
                        body.included_sessions,
                        body.price_minor,
                        user_id,
                        business,
                        program_id,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise SpecialVenuesStateError("Program code already exists") from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced location or currency not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, code, title, program_kind, capacity, enrolled_count, "
                "included_sessions, price_minor, currency, is_active, revision, recorded_by, "
                "recorded_at from gba.special_programs where tenant_id = %s and id = %s",
                (business, program_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _program_view(row)
        await commands.complete(conn, scope, view)
        return view


async def create_enrollment(
    conn: RuntimeConnection,
    business: UUID,
    enrollment_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: EnrollmentInput,
) -> EnrollmentView:
    _check_ready()
    await require_module(conn, business, SPECIAL_VENUES_MODULE)
    scope = IdempotencyScope(business, actor, "special.enrollment.create", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"enrollment_id": str(enrollment_id), **body.model_dump(mode="json")}),
        EnrollmentView,
    )
    if replay is not None:
        return replay

    async with module_writes(SPECIAL_VENUES_MODULE):
        prog = await (
            await conn.execute(
                "select capacity, enrolled_count, included_sessions from gba.special_programs "
                "where tenant_id = %s and location_id = %s and id = %s for update",
                (business, body.location_id, body.program_id),
            )
        ).fetchone()
        if prog is None:
            raise NotFoundError("Program not found in this branch")
        if int(prog[1]) + 1 > int(prog[0]):
            raise SpecialVenuesCapacityError("Program capacity reached")
        await conn.execute(
            "update gba.special_programs set enrolled_count = enrolled_count + 1, "
            "revision = revision + 1 where tenant_id = %s and id = %s",
            (business, body.program_id),
        )
        try:
            await conn.execute(
                "insert into gba.special_enrollments ("
                "id, tenant_id, location_id, program_id, participant_counterparty_id, "
                "status, sessions_used, sessions_total, revision, recorded_by"
                ") values (%s, %s, %s, %s, %s, 'active', 0, %s, 1, %s)",
                (
                    enrollment_id,
                    business,
                    body.location_id,
                    body.program_id,
                    body.participant_counterparty_id,
                    int(prog[2]),
                    user_id,
                ),
            )
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced participant counterparty not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, program_id, participant_counterparty_id, status, "
                "sessions_used, sessions_total, result_grade, revision, recorded_by, recorded_at "
                "from gba.special_enrollments where tenant_id = %s and id = %s",
                (business, enrollment_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _enrollment_view(row)
        await commands.complete(conn, scope, view)
        return view


async def use_enrollment_sessions(
    conn: RuntimeConnection,
    business: UUID,
    enrollment_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: EnrollmentSessionUseInput,
) -> EnrollmentView:
    _check_ready()
    await require_module(conn, business, SPECIAL_VENUES_MODULE)
    scope = IdempotencyScope(business, actor, "special.enrollment.use_sessions", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"enrollment_id": str(enrollment_id), **body.model_dump(mode="json")}),
        EnrollmentView,
    )
    if replay is not None:
        return replay

    async with module_writes(SPECIAL_VENUES_MODULE):
        cur = await (
            await conn.execute(
                "select status, sessions_used, sessions_total from gba.special_enrollments "
                "where tenant_id = %s and id = %s for update",
                (business, enrollment_id),
            )
        ).fetchone()
        if cur is None:
            raise NotFoundError("Enrollment not found")
        if str(cur[0]) != "active":
            raise SpecialVenuesStateError("Enrollment is not active")
        next_used = int(cur[1]) + body.sessions_delta
        total = int(cur[2])
        if next_used > total:
            raise SpecialVenuesCapacityError("Insufficient remaining sessions on enrollment")
        next_status = "completed" if next_used == total else "active"
        await conn.execute(
            "update gba.special_enrollments set sessions_used = %s, status = %s, "
            "result_grade = coalesce(%s, result_grade), revision = revision + 1, "
            "recorded_by = %s, recorded_at = now() where tenant_id = %s and id = %s",
            (next_used, next_status, body.result_grade, user_id, business, enrollment_id),
        )
        row = await (
            await conn.execute(
                "select id, location_id, program_id, participant_counterparty_id, status, "
                "sessions_used, sessions_total, result_grade, revision, recorded_by, recorded_at "
                "from gba.special_enrollments where tenant_id = %s and id = %s",
                (business, enrollment_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _enrollment_view(row)
        await commands.complete(conn, scope, view)
        return view


# ---------------------------------------------------------------------------
# Hospitality Rooms & Stays
# ---------------------------------------------------------------------------


async def save_room(
    conn: RuntimeConnection,
    business: UUID,
    room_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: RoomInput,
) -> RoomView:
    _check_ready()
    await require_module(conn, business, SPECIAL_VENUES_MODULE)
    scope = IdempotencyScope(business, actor, "special.room.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"room_id": str(room_id), **body.model_dump(mode="json")}),
        RoomView,
    )
    if replay is not None:
        return replay

    async with module_writes(SPECIAL_VENUES_MODULE):
        existing = await (
            await conn.execute(
                "select revision from gba.special_rooms where tenant_id = %s and id = %s "
                "for update",
                (business, room_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise SpecialVenuesStateError("Room does not exist yet")
                await conn.execute(
                    "insert into gba.special_rooms ("
                    "id, tenant_id, location_id, room_number, room_type, max_guests, "
                    "nightly_rate_minor, currency, housekeeping_status, revision, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s)",
                    (
                        room_id,
                        business,
                        body.location_id,
                        body.room_number,
                        body.room_type,
                        body.max_guests,
                        body.nightly_rate_minor,
                        body.currency,
                        body.housekeeping_status,
                        user_id,
                    ),
                )
            else:
                if body.expected_revision != int(existing[0]):
                    raise SpecialVenuesStateError("Room revision mismatch")
                await conn.execute(
                    "update gba.special_rooms set room_type = %s, max_guests = %s, "
                    "nightly_rate_minor = %s, housekeeping_status = %s, revision = revision + 1, "
                    "recorded_by = %s, recorded_at = now() where tenant_id = %s and id = %s",
                    (
                        body.room_type,
                        body.max_guests,
                        body.nightly_rate_minor,
                        body.housekeeping_status,
                        user_id,
                        business,
                        room_id,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise SpecialVenuesStateError("Room number already exists") from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced location or currency not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, room_number, room_type, max_guests, nightly_rate_minor, "
                "currency, housekeeping_status, revision, recorded_by, recorded_at "
                "from gba.special_rooms where tenant_id = %s and id = %s",
                (business, room_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _room_view(row)
        await commands.complete(conn, scope, view)
        return view


async def create_stay(
    conn: RuntimeConnection,
    business: UUID,
    stay_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: StayInput,
) -> StayView:
    _check_ready()
    await require_module(conn, business, SPECIAL_VENUES_MODULE)
    if body.check_out_date <= body.check_in_date:
        raise SpecialVenuesStateError("check_out_date must be after check_in_date")
    scope = IdempotencyScope(business, actor, "special.stay.create", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"stay_id": str(stay_id), **body.model_dump(mode="json")}),
        StayView,
    )
    if replay is not None:
        return replay

    async with module_writes(SPECIAL_VENUES_MODULE):
        room = await (
            await conn.execute(
                "select max_guests from gba.special_rooms "
                "where tenant_id = %s and location_id = %s and id = %s for update",
                (business, body.location_id, body.room_id),
            )
        ).fetchone()
        if room is None:
            raise NotFoundError("Room not found in this branch")
        if body.guest_count > int(room[0]):
            raise SpecialVenuesCapacityError("Guest count exceeds room max_guests")
        try:
            await conn.execute(
                "insert into gba.special_stays ("
                "id, tenant_id, location_id, room_id, guest_counterparty_id, check_in_date, "
                "check_out_date, guest_count, status, revision, recorded_by"
                ") values (%s, %s, %s, %s, %s, %s, %s, %s, 'reserved', 1, %s)",
                (
                    stay_id,
                    business,
                    body.location_id,
                    body.room_id,
                    body.guest_counterparty_id,
                    body.check_in_date,
                    body.check_out_date,
                    body.guest_count,
                    user_id,
                ),
            )
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced guest counterparty not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, room_id, guest_counterparty_id, check_in_date, "
                "check_out_date, guest_count, status, checked_in_at, checked_out_at, revision, "
                "recorded_by, recorded_at from gba.special_stays where tenant_id = %s and id = %s",
                (business, stay_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _stay_view(row)
        await commands.complete(conn, scope, view)
        return view


async def transition_stay(
    conn: RuntimeConnection,
    business: UUID,
    stay_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: StayTransitionInput,
) -> StayView:
    _check_ready()
    await require_module(conn, business, SPECIAL_VENUES_MODULE)
    scope = IdempotencyScope(business, actor, "special.stay.transition", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"stay_id": str(stay_id), **body.model_dump(mode="json")}),
        StayView,
    )
    if replay is not None:
        return replay

    async with module_writes(SPECIAL_VENUES_MODULE):
        st = await (
            await conn.execute(
                "select room_id, status from gba.special_stays "
                "where tenant_id = %s and id = %s for update",
                (business, stay_id),
            )
        ).fetchone()
        if st is None:
            raise NotFoundError("Stay not found")
        room_id, status = st[0], str(st[1])
        rm = await (
            await conn.execute(
                "select housekeeping_status from gba.special_rooms "
                "where tenant_id = %s and id = %s for update",
                (business, room_id),
            )
        ).fetchone()
        assert rm is not None  # noqa: S101
        hk = str(rm[0])

        if body.action == "check_in":
            if status != "reserved":
                raise SpecialVenuesStateError("Only reserved stays can check in")
            if hk != "clean":
                raise SpecialVenuesStateError(
                    f"Room cannot be checked in while housekeeping_status is {hk}"
                )
            await conn.execute(
                "update gba.special_rooms set housekeeping_status = 'occupied', "
                "revision = revision + 1 where tenant_id = %s and id = %s",
                (business, room_id),
            )
            await conn.execute(
                "update gba.special_stays set status = 'checked_in', checked_in_at = now(), "
                "revision = revision + 1, recorded_by = %s, recorded_at = now() "
                "where tenant_id = %s and id = %s",
                (user_id, business, stay_id),
            )
        elif body.action == "check_out":
            if status != "checked_in":
                raise SpecialVenuesStateError("Only checked-in stays can check out")
            await conn.execute(
                "update gba.special_rooms set housekeeping_status = 'dirty', "
                "revision = revision + 1 where tenant_id = %s and id = %s",
                (business, room_id),
            )
            await conn.execute(
                "update gba.special_stays set status = 'checked_out', checked_out_at = now(), "
                "revision = revision + 1, recorded_by = %s, recorded_at = now() "
                "where tenant_id = %s and id = %s",
                (user_id, business, stay_id),
            )
        else:
            if status != "reserved":
                raise SpecialVenuesStateError("Only reserved stays can be cancelled")
            await conn.execute(
                "update gba.special_stays set status = 'cancelled', revision = revision + 1, "
                "recorded_by = %s, recorded_at = now() where tenant_id = %s and id = %s",
                (user_id, business, stay_id),
            )

        row = await (
            await conn.execute(
                "select id, location_id, room_id, guest_counterparty_id, check_in_date, "
                "check_out_date, guest_count, status, checked_in_at, checked_out_at, revision, "
                "recorded_by, recorded_at from gba.special_stays where tenant_id = %s and id = %s",
                (business, stay_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _stay_view(row)
        await commands.complete(conn, scope, view)
        return view


# ---------------------------------------------------------------------------
# Events & Tickets
# ---------------------------------------------------------------------------


async def save_event(
    conn: RuntimeConnection,
    business: UUID,
    event_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: EventInput,
) -> EventView:
    _check_ready()
    await require_module(conn, business, SPECIAL_VENUES_MODULE)
    scope = IdempotencyScope(business, actor, "special.event.save", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"event_id": str(event_id), **body.model_dump(mode="json")}),
        EventView,
    )
    if replay is not None:
        return replay

    async with module_writes(SPECIAL_VENUES_MODULE):
        existing = await (
            await conn.execute(
                "select revision, tickets_sold from gba.special_events "
                "where tenant_id = %s and id = %s for update",
                (business, event_id),
            )
        ).fetchone()
        try:
            if existing is None:
                if body.expected_revision != 0:
                    raise SpecialVenuesStateError("Event does not exist yet")
                await conn.execute(
                    "insert into gba.special_events ("
                    "id, tenant_id, location_id, code, title, event_date, capacity, "
                    "tickets_sold, ticket_price_minor, currency, status, revision, recorded_by"
                    ") values (%s, %s, %s, %s, %s, %s, %s, 0, %s, %s, 'scheduled', 1, %s)",
                    (
                        event_id,
                        business,
                        body.location_id,
                        body.code,
                        body.title,
                        body.event_date,
                        body.capacity,
                        body.ticket_price_minor,
                        body.currency,
                        user_id,
                    ),
                )
            else:
                if body.expected_revision != int(existing[0]):
                    raise SpecialVenuesStateError("Event revision mismatch")
                if body.capacity < int(existing[1]):
                    raise SpecialVenuesCapacityError("Capacity cannot be below sold tickets")
                await conn.execute(
                    "update gba.special_events set title = %s, event_date = %s, capacity = %s, "
                    "ticket_price_minor = %s, revision = revision + 1, recorded_by = %s, "
                    "recorded_at = now() where tenant_id = %s and id = %s",
                    (
                        body.title,
                        body.event_date,
                        body.capacity,
                        body.ticket_price_minor,
                        user_id,
                        business,
                        event_id,
                    ),
                )
        except errors.UniqueViolation as exc:
            raise SpecialVenuesStateError("Event code already exists") from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced location or currency not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, code, title, event_date, capacity, tickets_sold, "
                "ticket_price_minor, currency, status, revision, recorded_by, recorded_at "
                "from gba.special_events where tenant_id = %s and id = %s",
                (business, event_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _event_view(row)
        await commands.complete(conn, scope, view)
        return view


async def issue_ticket(
    conn: RuntimeConnection,
    business: UUID,
    ticket_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: TicketInput,
) -> TicketView:
    _check_ready()
    await require_module(conn, business, SPECIAL_VENUES_MODULE)
    scope = IdempotencyScope(business, actor, "special.ticket.issue", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"ticket_id": str(ticket_id), **body.model_dump(mode="json")}),
        TicketView,
    )
    if replay is not None:
        return replay

    async with module_writes(SPECIAL_VENUES_MODULE):
        ev = await (
            await conn.execute(
                "select capacity, tickets_sold, status from gba.special_events "
                "where tenant_id = %s and location_id = %s and id = %s for update",
                (business, body.location_id, body.event_id),
            )
        ).fetchone()
        if ev is None:
            raise NotFoundError("Event not found in this branch")
        if str(ev[2]) != "scheduled":
            raise SpecialVenuesStateError("Cannot issue tickets for non-scheduled event")
        if int(ev[1]) + body.quantity > int(ev[0]):
            raise SpecialVenuesCapacityError("Event ticket capacity exceeded")
        await conn.execute(
            "update gba.special_events set tickets_sold = tickets_sold + %s, "
            "revision = revision + 1 where tenant_id = %s and id = %s",
            (body.quantity, business, body.event_id),
        )
        try:
            await conn.execute(
                "insert into gba.special_tickets ("
                "id, tenant_id, location_id, event_id, attendee_counterparty_id, ticket_code, "
                "quantity, status, revision, recorded_by"
                ") values (%s, %s, %s, %s, %s, %s, %s, 'issued', 1, %s)",
                (
                    ticket_id,
                    business,
                    body.location_id,
                    body.event_id,
                    body.attendee_counterparty_id,
                    body.ticket_code,
                    body.quantity,
                    user_id,
                ),
            )
        except errors.UniqueViolation as exc:
            raise SpecialVenuesStateError("Ticket code already exists for event") from exc
        except errors.ForeignKeyViolation as exc:
            raise InvalidReferenceError("Referenced attendee counterparty not found") from exc

        row = await (
            await conn.execute(
                "select id, location_id, event_id, attendee_counterparty_id, ticket_code, "
                "quantity, status, checked_in_at, revision, recorded_by, recorded_at "
                "from gba.special_tickets where tenant_id = %s and id = %s",
                (business, ticket_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _ticket_view(row)
        await commands.complete(conn, scope, view)
        return view


async def transition_ticket(
    conn: RuntimeConnection,
    business: UUID,
    ticket_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: TicketTransitionInput,
) -> TicketView:
    _check_ready()
    await require_module(conn, business, SPECIAL_VENUES_MODULE)
    scope = IdempotencyScope(business, actor, "special.ticket.transition", key)
    replay = await commands.claim(
        conn,
        scope,
        commands.fingerprint({"ticket_id": str(ticket_id), **body.model_dump(mode="json")}),
        TicketView,
    )
    if replay is not None:
        return replay

    async with module_writes(SPECIAL_VENUES_MODULE):
        tk = await (
            await conn.execute(
                "select event_id, quantity, status from gba.special_tickets "
                "where tenant_id = %s and id = %s for update",
                (business, ticket_id),
            )
        ).fetchone()
        if tk is None:
            raise NotFoundError("Ticket not found")
        event_id, qty, status = tk[0], int(tk[1]), str(tk[2])
        if body.action == "check_in":
            if status != "issued":
                raise SpecialVenuesStateError("Only issued tickets can check in")
            await conn.execute(
                "update gba.special_tickets set status = 'checked_in', checked_in_at = now(), "
                "revision = revision + 1, recorded_by = %s, recorded_at = now() "
                "where tenant_id = %s and id = %s",
                (user_id, business, ticket_id),
            )
        else:
            if status != "issued":
                raise SpecialVenuesStateError("Only issued tickets can be cancelled")
            await conn.execute(
                "update gba.special_events set tickets_sold = tickets_sold - %s, "
                "revision = revision + 1 where tenant_id = %s and id = %s",
                (qty, business, event_id),
            )
            await conn.execute(
                "update gba.special_tickets set status = 'cancelled', revision = revision + 1, "
                "recorded_by = %s, recorded_at = now() where tenant_id = %s and id = %s",
                (user_id, business, ticket_id),
            )

        row = await (
            await conn.execute(
                "select id, location_id, event_id, attendee_counterparty_id, ticket_code, "
                "quantity, status, checked_in_at, revision, recorded_by, recorded_at "
                "from gba.special_tickets where tenant_id = %s and id = %s",
                (business, ticket_id),
            )
        ).fetchone()
        assert row is not None  # noqa: S101
        view = _ticket_view(row)
        await commands.complete(conn, scope, view)
        return view
