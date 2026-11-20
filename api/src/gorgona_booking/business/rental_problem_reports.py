"""RENT-01 R-09: problem reports on a rental booking.

A customer company answering on the platform reports a problem through its live grant with
rental.customer_answer (source platform, with the grant and the customer binding it answered
under). Otherwise the business records the report with its source and the reporter's name.
Reports are insert-only and numbered per booking; the database rechecks every rule.
"""

from datetime import UTC, datetime
from typing import Annotated, Any, Literal
from uuid import UUID

from psycopg.errors import CheckViolation
from pydantic import AfterValidator, AwareDatetime, BaseModel, Field

from gorgona_booking.booking import idempotency
from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.booking.models import IdempotencyKeyReusedError
from gorgona_booking.business.module_gate import RENTAL_MODULE, module_writes
from gorgona_booking.business.rental import (
    RentalRevisionConflictError,
    Strict,
    fingerprint,
    require_rental,
)
from gorgona_booking.business.rental_customer_answer import (
    authorized_binding,
    plain_line,
    plain_text,
)
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, DomainError, NotFoundError
from gorgona_booking.tenancy.authorization import DelegationScope, PermissionDeniedError


class RentalProblemBookingCancelledError(ConflictError):
    code = "RENTAL_BOOKING_CANCELLED"


class RentalFutureTimeError(ConflictError):
    code = "RENTAL_FUTURE_TIME"


class RentalProblemTooEarlyError(DomainError):
    """The table keeps moments from 2000-01-01 on; an earlier one is an invalid request (422)."""

    code = "RENTAL_PROBLEM_TOO_EARLY"


EARLIEST_PROBLEM = datetime(2000, 1, 1, tzinfo=UTC)


def _text(value: str) -> str:
    if not value.strip():
        raise ValueError("text that is not only blanks")
    return value


def _since_2000(value: datetime) -> datetime:
    if value < EARLIEST_PROBLEM:
        raise ValueError("a moment from 2000-01-01 on")
    return value


Kind = Literal["breakdown", "damage", "accident", "other"]
Description = Annotated[
    str, AfterValidator(_text), AfterValidator(plain_text), Field(min_length=1, max_length=2000)
]
Name = Annotated[
    str, AfterValidator(_text), AfterValidator(plain_line), Field(min_length=1, max_length=200)
]
Occurred = Annotated[AwareDatetime, AfterValidator(_since_2000)]
Revision = Annotated[int, Field(ge=1, le=2_147_483_647)]


class StaffProblemInput(Strict):
    schema_version: Literal[1]
    kind: Kind
    description: Description
    occurred_at: Occurred
    source: Literal["phone", "email", "paper"]
    reported_by: Name


class CustomerProblemInput(Strict):
    schema_version: Literal[1]
    binding_revision: Revision
    kind: Kind
    description: Description
    occurred_at: Occurred


class ProblemReport(BaseModel):
    schema_version: Literal[1] = 1
    booking_id: UUID
    number: int
    kind: Kind
    description: str
    occurred_at: datetime
    source: Literal["platform", "phone", "email", "paper"]
    reported_by: str | None
    company_id: UUID | None
    # The grant's name for the customer company of a platform report, where the session can
    # read the grant (company-wide staff and the company's delegates); otherwise null.
    company_name: str | None = None
    recorded_at: datetime


class ProblemList(BaseModel):
    schema_version: Literal[1] = 1
    booking_id: UUID
    items: list[ProblemReport]


class CustomerProblemList(ProblemList):
    binding_revision: int


def _report(booking_id: UUID, row: tuple[Any, ...]) -> ProblemReport:
    return ProblemReport(
        booking_id=booking_id,
        number=row[0],
        kind=row[1],
        description=row[2],
        occurred_at=row[3],
        source=row[4],
        reported_by=row[5],
        company_id=row[6],
        recorded_at=row[7],
        company_name=row[8],
    )


_REPORT_COLUMNS = (
    "select r.number, r.kind, r.description, r.occurred_at, r.source, r.reported_by, "
    "r.company_id, r.created_at, g.servicer_display_name "
    "from gba.rental_problem_reports r left join gba.delegation_grants g "
    "on (g.owner_tenant_id, g.id, g.servicer_tenant_id) = (r.tenant_id, r.grant_id, r.company_id) "
)


async def _reports(
    conn: RuntimeConnection,
    booking_id: UUID,
    company: UUID | None = None,
    number: int | None = None,
) -> list[ProblemReport]:
    cursor = await conn.execute(
        _REPORT_COLUMNS + "where r.booking_id = %s "
        "and (%s::uuid is null or r.company_id = %s) "
        "and (%s::integer is null or r.number = %s) order by r.number",
        (booking_id, company, company, number, number),
    )
    return [_report(booking_id, row) for row in await cursor.fetchall()]


async def _visible(conn: RuntimeConnection, booking_id: UUID) -> None:
    row = await (
        await conn.execute("select 1 from gba.rental_bookings where id = %s", (booking_id,))
    ).fetchone()
    if row is None:
        raise NotFoundError("Booking not found", booking_id=str(booking_id))


async def list_reports(conn: RuntimeConnection, booking_id: UUID) -> ProblemList:
    await _visible(conn, booking_id)
    return ProblemList(booking_id=booking_id, items=await _reports(conn, booking_id))


async def _insert(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    user_id: UUID,
    fields: dict[str, Any],
) -> ProblemReport:
    await conn.execute("select gba.lock_rental_booking_class(%s, %s)", (business, booking_id))
    numbered = await (
        await conn.execute(
            "select coalesce(max(number), 0) + 1 from gba.rental_problem_reports "
            "where booking_id = %s",
            (booking_id,),
        )
    ).fetchone()
    number = int(numbered[0]) if numbered else 1
    try:
        async with module_writes(RENTAL_MODULE), conn.transaction():
            row = await (
                await conn.execute(
                    "insert into gba.rental_problem_reports (tenant_id, booking_id, number, kind, "
                    "description, occurred_at, source, reported_by, company_id, grant_id, "
                    "binding_revision, recorded_by) values (%s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "%s, %s, %s) returning number",
                    (
                        business,
                        booking_id,
                        number,
                        fields["kind"],
                        fields["description"],
                        fields["occurred_at"],
                        fields["source"],
                        fields.get("reported_by"),
                        fields.get("company_id"),
                        fields.get("grant_id"),
                        fields.get("binding_revision"),
                        user_id,
                    ),
                )
            ).fetchone()
    except CheckViolation as exc:
        name = exc.diag.constraint_name
        if name == "rental_problem_reports_booking_check":
            raise RentalProblemBookingCancelledError(
                "The booking is cancelled", booking_id=str(booking_id)
            ) from exc
        if name == "rental_problem_reports_time_check":
            raise RentalFutureTimeError("A problem is reported after it happened") from exc
        if name == "rental_problem_reports_occurred_check":
            raise RentalProblemTooEarlyError("A problem happened on 2000-01-01 or later") from exc
        if name == "rental_problem_reports_customer_scope":
            raise PermissionDeniedError("Customer grant does not authorize this booking") from exc
        raise
    if row is None:
        raise RuntimeError("PostgreSQL did not return the problem report")
    saved = await _reports(conn, booking_id, number=int(row[0]))
    if len(saved) != 1:
        raise RuntimeError("PostgreSQL did not return the problem report")
    return saved[0]


async def record_report(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: StaffProblemInput,
) -> ProblemReport:
    """The business records a report given off the platform, with its source and reporter."""
    await require_rental(conn, business)
    scope = IdempotencyScope(business, actor, "rental.problem", key)
    request = fingerprint(str(booking_id), body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return ProblemReport.model_validate(stored.body)
    await _visible(conn, booking_id)
    report = await _insert(
        conn,
        business,
        booking_id,
        user_id,
        {
            "kind": body.kind,
            "description": body.description,
            "occurred_at": body.occurred_at,
            "source": body.source,
            "reported_by": body.reported_by,
        },
    )
    await idempotency.complete(conn, scope, 200, report.model_dump(mode="json"))
    return report


async def customer_reports(
    conn: RuntimeConnection, business: UUID, booking_id: UUID, delegation: DelegationScope
) -> CustomerProblemList:
    """The customer company's own platform reports and the binding to answer under."""
    binding = await authorized_binding(conn, business, booking_id, delegation, lock=False)
    return CustomerProblemList(
        booking_id=booking_id,
        binding_revision=binding.revision,
        items=await _reports(conn, booking_id, delegation.servicer_business_id),
    )


async def report_as_customer(
    conn: RuntimeConnection,
    business: UUID,
    booking_id: UUID,
    delegation: DelegationScope,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: CustomerProblemInput,
) -> ProblemReport:
    """The customer company reports a problem through its live grant (source platform)."""
    binding = await authorized_binding(conn, business, booking_id, delegation, lock=True)
    # A retry returns the stored report before the revision check, so a later re-save of the
    # binding cannot block it.
    scope = IdempotencyScope(business, actor, "rental.customer_problem", key)
    request = fingerprint(f"{booking_id}:{delegation.grant_id}", body)
    stored = await idempotency.claim(conn, scope, request)
    if stored is not None:
        if stored.request_hash != request:
            raise IdempotencyKeyReusedError("Key was used for another request")
        return ProblemReport.model_validate(stored.body)
    if body.binding_revision != binding.revision:
        raise RentalRevisionConflictError("The customer company changed since it was read")
    report = await _insert(
        conn,
        business,
        booking_id,
        user_id,
        {
            "kind": body.kind,
            "description": body.description,
            "occurred_at": body.occurred_at,
            "source": "platform",
            "company_id": delegation.servicer_business_id,
            "grant_id": delegation.grant_id,
            "binding_revision": binding.revision,
        },
    )
    await idempotency.complete(conn, scope, 200, report.model_dump(mode="json"))
    return report
