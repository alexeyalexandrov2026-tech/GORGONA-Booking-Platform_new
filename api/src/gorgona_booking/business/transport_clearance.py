"""M5 (package M, TMS-03): hours-of-service profiles, telematics freshness and clearance (ADR-0032).

Profiles are insert-only versions; duty records and pings are insert-only facts with a source record
id. Clearance is computed for a moment and never stored: stale or unknown data is never `cleared`.
"""

import unicodedata
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from itertools import pairwise
from typing import Any, Literal, Self
from uuid import UUID, uuid7

from psycopg.errors import ExclusionViolation, UniqueViolation
from pydantic import AwareDatetime, BaseModel, Field, model_validator

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.module_gate import TRANSPORT_MODULE, module_writes
from gorgona_booking.business.transport import (
    TransportRevisionConflictError,
    _fingerprint,
    _Strict,
    require_transport,
    trip_span,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, NotFoundError

DutyStatus = Literal["off_duty", "sleeper", "driving", "on_duty"]
Status = Literal["cleared", "not_cleared", "unknown"]
WORK = frozenset({"driving", "on_duty"})
_SOURCE = r"^[a-z][a-z0-9_.-]{0,31}$"


class TransportFactConflictError(ConflictError):
    code = "TRANSPORT_FACT_CONFLICT"


class TransportDutyOverlapError(ConflictError):
    code = "TRANSPORT_DUTY_OVERLAP"


def _visible(value: str) -> None:
    if not value.strip() or any(unicodedata.category(ch) == "Cc" for ch in value):
        raise ValueError("a source record id has visible text and no control characters")


class ProfileInput(_Strict):
    schema_version: Literal[1]
    expected_revision: int = Field(ge=0, le=2_147_483_647)
    code: str = Field(pattern=r"^[A-Z][A-Z0-9_]{0,63}$")
    max_driving_minutes: int = Field(ge=1, le=1440)
    max_window_minutes: int = Field(ge=1, le=1440)
    reset_minutes: int = Field(ge=1, le=2880)
    cycle_minutes: int = Field(ge=1, le=20160)
    cycle_days: int = Field(ge=1, le=14)
    max_data_age_minutes: int = Field(ge=1, le=1440)


class ProfileView(BaseModel):
    revision: int
    code: str
    max_driving_minutes: int
    max_window_minutes: int
    reset_minutes: int
    cycle_minutes: int
    cycle_days: int
    max_data_age_minutes: int


class DutyInput(_Strict):
    schema_version: Literal[1]
    source: str = Field(pattern=_SOURCE)
    source_record_id: str = Field(min_length=1, max_length=200)
    status: DutyStatus
    starts_at: AwareDatetime
    ends_at: AwareDatetime

    @model_validator(mode="after")
    def _shape(self) -> Self:
        _visible(self.source_record_id)
        if self.starts_at >= self.ends_at:
            raise ValueError("a duty record starts before it ends")
        return self


class DutyView(BaseModel):
    record_id: UUID
    driver_id: UUID
    status: str
    starts_at: datetime
    ends_at: datetime
    source: str
    source_record_id: str


class PingInput(_Strict):
    schema_version: Literal[1]
    source: str = Field(pattern=_SOURCE)
    source_record_id: str = Field(min_length=1, max_length=200)
    observed_at: AwareDatetime

    @model_validator(mode="after")
    def _shape(self) -> Self:
        _visible(self.source_record_id)
        return self


class PingView(BaseModel):
    ping_id: UUID
    vehicle_id: UUID
    observed_at: datetime
    source: str
    source_record_id: str


class ProfileRef(BaseModel):
    code: str
    revision: int


class RoleClearance(BaseModel):
    role: str
    resource_id: UUID | None
    status: Status
    reasons: list[str]


class ClearanceView(BaseModel):
    trip_id: UUID
    at: datetime
    status: Status
    profile: ProfileRef | None
    roles: list[RoleClearance]


_PROFILE = (
    "select revision, code, max_driving_minutes, max_window_minutes, reset_minutes, "
    "cycle_minutes, cycle_days, max_data_age_minutes from gba.transport_hos_profiles "
    "order by revision desc limit 1"
)


def _profile(row: tuple[Any, ...]) -> ProfileView:
    return ProfileView.model_validate(dict(zip(ProfileView.model_fields, row, strict=True)))


async def load_profile(conn: RuntimeConnection) -> ProfileView | None:
    row = await (await conn.execute(_PROFILE)).fetchone()
    return None if row is None else _profile(row)


async def save_profile(
    conn: RuntimeConnection,
    business: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ProfileInput,
) -> ProfileView:
    """Replace the business's rule profile with the expected revision (decision 1)."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.hos_profile", key)
    fingerprint = _fingerprint(business, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None:
        if stored.request_hash != fingerprint:
            raise IdempotencyKeyReusedError("Key was used for another request")
        view = await load_profile(conn)
        if view is None:
            raise NotFoundError("No hours-of-service profile")
        return view
    await conn.execute(
        "select pg_catalog.pg_advisory_xact_lock(pg_catalog.hashtextextended(%s, 0))",
        (f"gba:hos-profile:{business}",),
    )
    current = await load_profile(conn)
    found = 0 if current is None else current.revision
    if found != body.expected_revision:
        raise TransportRevisionConflictError(
            "The profile changed since it was read; reload it", revision=found
        )
    async with module_writes(TRANSPORT_MODULE), conn.transaction():
        await conn.execute(
            "insert into gba.transport_hos_profiles (tenant_id, revision, code, "
            "max_driving_minutes, max_window_minutes, reset_minutes, cycle_minutes, cycle_days, "
            "max_data_age_minutes, created_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
            (
                business,
                found + 1,
                body.code,
                body.max_driving_minutes,
                body.max_window_minutes,
                body.reset_minutes,
                body.cycle_minutes,
                body.cycle_days,
                body.max_data_age_minutes,
                user_id,
            ),
        )
    view = await load_profile(conn)
    assert view is not None  # noqa: S101 - inserted above
    await idempotency.complete(conn, scope, 200, {"revision": view.revision})
    return view


def _utc(value: datetime) -> datetime:
    return value.astimezone(UTC)


async def record_duty(
    conn: RuntimeConnection,
    business: UUID,
    driver_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: DutyInput,
) -> DutyView:
    """Record a driver's duty status over an interval; a repeat changes nothing (decision 2)."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.duty", key)
    fingerprint = _fingerprint(driver_id, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None and stored.request_hash != fingerprint:
        raise IdempotencyKeyReusedError("Key was used for another request")
    driver = await (
        await conn.execute("select 1 from gba.transport_drivers where id = %s", (driver_id,))
    ).fetchone()
    if driver is None:
        raise NotFoundError("Driver not found", driver_id=str(driver_id))
    query = (
        "select id, driver_id, status, starts_at, ends_at, source, source_record_id "
        "from gba.transport_duty_records where source = %s and source_record_id = %s"
    )
    row = await (await conn.execute(query, (body.source, body.source_record_id))).fetchone()
    if row is None and stored is None:
        try:
            async with module_writes(TRANSPORT_MODULE), conn.transaction():
                await conn.execute(
                    "insert into gba.transport_duty_records (tenant_id, id, driver_id, status, "
                    "starts_at, ends_at, source, source_record_id, recorded_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        uuid7(),
                        driver_id,
                        body.status,
                        body.starts_at,
                        body.ends_at,
                        body.source,
                        body.source_record_id,
                        user_id,
                    ),
                )
        except ExclusionViolation as exc:
            raise TransportDutyOverlapError(
                "A driver's duty records never overlap", driver_id=str(driver_id)
            ) from exc
        except UniqueViolation as exc:
            raise TransportFactConflictError("This source record id is already recorded") from exc
        row = await (await conn.execute(query, (body.source, body.source_record_id))).fetchone()
    assert row is not None  # noqa: S101 - recorded above or before
    view = DutyView(
        record_id=row[0],
        driver_id=row[1],
        status=row[2],
        starts_at=_utc(row[3]),
        ends_at=_utc(row[4]),
        source=row[5],
        source_record_id=row[6],
    )
    if (view.driver_id, view.status, view.starts_at, view.ends_at) != (
        driver_id,
        body.status,
        body.starts_at,
        body.ends_at,
    ):
        raise TransportFactConflictError(
            "This source record id was recorded with other content",
            source=body.source,
            source_record_id=body.source_record_id,
        )
    if stored is None:
        await idempotency.complete(conn, scope, 200, {"record_id": str(view.record_id)})
    return view


async def record_ping(
    conn: RuntimeConnection,
    business: UUID,
    vehicle_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: PingInput,
) -> PingView:
    """Record a vehicle's telematics observation; a repeat changes nothing (decision 2)."""
    await require_transport(conn, business)
    scope = IdempotencyScope(business, actor, "transport.ping", key)
    fingerprint = _fingerprint(vehicle_id, body)
    stored = await idempotency.claim(conn, scope, fingerprint)
    if stored is not None and stored.request_hash != fingerprint:
        raise IdempotencyKeyReusedError("Key was used for another request")
    vehicle = await (
        await conn.execute("select 1 from gba.transport_vehicles where id = %s", (vehicle_id,))
    ).fetchone()
    if vehicle is None:
        raise NotFoundError("Vehicle not found", vehicle_id=str(vehicle_id))
    query = (
        "select id, vehicle_id, observed_at, source, source_record_id "
        "from gba.transport_telematics_pings where source = %s and source_record_id = %s"
    )
    row = await (await conn.execute(query, (body.source, body.source_record_id))).fetchone()
    if row is None and stored is None:
        try:
            async with module_writes(TRANSPORT_MODULE), conn.transaction():
                await conn.execute(
                    "insert into gba.transport_telematics_pings (tenant_id, id, vehicle_id, "
                    "observed_at, source, source_record_id, recorded_by) "
                    "values (%s, %s, %s, %s, %s, %s, %s)",
                    (
                        business,
                        uuid7(),
                        vehicle_id,
                        body.observed_at,
                        body.source,
                        body.source_record_id,
                        user_id,
                    ),
                )
        except UniqueViolation as exc:
            raise TransportFactConflictError("This source record id is already recorded") from exc
        row = await (await conn.execute(query, (body.source, body.source_record_id))).fetchone()
    assert row is not None  # noqa: S101 - recorded above or before
    view = PingView(
        ping_id=row[0],
        vehicle_id=row[1],
        observed_at=_utc(row[2]),
        source=row[3],
        source_record_id=row[4],
    )
    if (view.vehicle_id, view.observed_at) != (vehicle_id, body.observed_at):
        raise TransportFactConflictError(
            "This source record id was recorded with other content",
            source=body.source,
            source_record_id=body.source_record_id,
        )
    if stored is None:
        await idempotency.complete(conn, scope, 200, {"ping_id": str(view.ping_id)})
    return view


@dataclass(frozen=True, slots=True)
class Duty:
    status: str
    starts_at: datetime
    ends_at: datetime


def _minutes(start: datetime, end: datetime) -> float:
    return max((end - start).total_seconds(), 0) / 60


def evaluate_driver(
    records: list[Duty], profile: ProfileView, at: datetime
) -> tuple[Status, list[str]]:
    """Judge a driver at `at` from their duty records (decisions 3 and 4)."""
    rows = sorted(
        (Duty(r.status, r.starts_at, min(r.ends_at, at)) for r in records if r.starts_at < at),
        key=lambda r: r.starts_at,
    )
    if not rows:
        return "unknown", ["no_duty_data"]
    latest = max(r.ends_at for r in rows)
    since = at - timedelta(days=profile.cycle_days)
    window = [r for r in rows if r.ends_at > since]
    reasons: list[str] = []
    if at - latest > timedelta(minutes=profile.max_data_age_minutes):
        reasons.append("stale_duty_data")
    contiguous = all(a.ends_at == b.starts_at for a, b in pairwise(window))
    if not window or window[0].starts_at > since or not contiguous:
        reasons.append("incomplete_duty_data")
    if reasons:
        return "unknown", reasons
    # The last run of off-duty or sleeper time long enough to reset the daily limits.
    reset_end, run_start = since, None
    for row in window:
        if row.status in WORK:
            run_start = None
            continue
        run_start = run_start or max(row.starts_at, since)
        if _minutes(run_start, row.ends_at) >= profile.reset_minutes:
            reset_end = row.ends_at
    work = [r for r in window if r.status in WORK and r.ends_at > reset_end]
    driving = sum(
        _minutes(max(r.starts_at, reset_end), r.ends_at) for r in work if r.status == "driving"
    )
    duty_window = _minutes(min(max(r.starts_at, reset_end) for r in work), latest) if work else 0.0
    cycle = sum(_minutes(max(r.starts_at, since), r.ends_at) for r in window if r.status in WORK)
    limits = [
        reason
        for reason, exceeded in (
            ("driving_limit", driving > profile.max_driving_minutes),
            ("window_limit", duty_window > profile.max_window_minutes),
            ("cycle_limit", cycle > profile.cycle_minutes),
        )
        if exceeded
    ]
    return ("not_cleared", limits) if limits else ("cleared", [])


def evaluate_vehicle(
    observed: datetime | None, profile: ProfileView, at: datetime
) -> tuple[Status, list[str]]:
    if observed is None:
        return "unknown", ["no_telematics"]
    if at - observed > timedelta(minutes=profile.max_data_age_minutes):
        return "unknown", ["stale_telematics"]
    return "cleared", []


_DUTY = (
    "select r.status, r.starts_at, r.ends_at from gba.transport_duty_records r "
    "join gba.transport_drivers d "
    "on d.tenant_id = r.tenant_id and d.id = r.driver_id "
    "where d.resource_id = %s and r.starts_at < %s order by r.starts_at"
)
_PING = (
    "select max(p.observed_at) from gba.transport_telematics_pings p "
    "join gba.transport_vehicles v "
    "on v.tenant_id = p.tenant_id and v.id = p.vehicle_id "
    "where v.resource_id = %s and p.observed_at <= %s"
)


async def _role(
    conn: RuntimeConnection,
    role: str,
    resource: UUID,
    profile: ProfileView | None,
    at: datetime,
) -> RoleClearance:
    if profile is None:
        return RoleClearance(
            role=role, resource_id=resource, status="unknown", reasons=["no_hos_profile"]
        )
    if role == "driver":
        rows = await (await conn.execute(_DUTY, (resource, at))).fetchall()
        status, reasons = evaluate_driver([Duty(*row) for row in rows], profile, at)
    else:
        row = await (await conn.execute(_PING, (resource, at))).fetchone()
        status, reasons = evaluate_vehicle(None if row is None else row[0], profile, at)
    return RoleClearance(role=role, resource_id=resource, status=status, reasons=reasons)


async def clearance(conn: RuntimeConnection, trip_id: UUID, at: datetime) -> ClearanceView:
    """Clear a trip at `at` only when every role is known, fresh and within the limits."""
    trip = await (
        await conn.execute("select 1 from gba.transport_trips where id = %s", (trip_id,))
    ).fetchone()
    if trip is None:
        raise NotFoundError("Trip not found", trip_id=str(trip_id))
    profile = await load_profile(conn)
    span = await trip_span(conn, trip_id)
    span_end = None if span is None else span[1]
    periods = await (
        await conn.execute(
            "select a.role, a.resource_id, a.starts_at, e.ends_at "
            "from gba.transport_assignments a left join gba.transport_assignment_ends e "
            "on e.tenant_id = a.tenant_id and e.assignment_id = a.id "
            "where a.trip_id = %s order by a.starts_at, a.created_at",
            (trip_id,),
        )
    ).fetchall()
    # The period that holds the moment; otherwise the open one of that role.
    chosen: dict[str, UUID] = {}
    for role, resource, start, end in periods:
        stop = end or span_end
        if start <= at and (stop is None or at < stop):
            chosen[role] = resource
    for role, resource, _, end in periods:
        if role not in chosen and end is None:
            chosen[role] = resource
    roles: list[RoleClearance] = []
    for role in ("driver", "truck", "trailer"):
        resource = chosen.get(role)
        if resource is not None:
            roles.append(await _role(conn, role, resource, profile, at))
        elif role != "trailer":
            roles.append(
                RoleClearance(role=role, resource_id=None, status="unknown", reasons=["unassigned"])
            )
    statuses = {item.status for item in roles}
    overall: Status = (
        "not_cleared"
        if "not_cleared" in statuses
        else "unknown"
        if "unknown" in statuses
        else "cleared"
    )
    return ClearanceView(
        trip_id=trip_id,
        at=_utc(at),
        status=overall,
        profile=None
        if profile is None
        else ProfileRef(code=profile.code, revision=profile.revision),
        roles=roles,
    )
