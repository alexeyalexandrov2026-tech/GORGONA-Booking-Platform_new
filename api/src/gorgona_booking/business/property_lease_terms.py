"""Signed extensions and release of an exclusive property lease."""

from datetime import date
from typing import Literal
from uuid import UUID

from psycopg import errors
from psycopg.rows import class_row
from pydantic import AwareDatetime, Field, StrictInt

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, modules
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.property_catalog import PROPERTY_MODULE, PropertyNotReadyError
from gorgona_booking.business.property_leases import LeaseOverlapError, get_lease
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError

_SELECT = """
select l.id as lease_id, t.revision, t.action, t.agreement_revision,
       v.document_id, v.document_revision, v.terminated_on, l.starts_on,
       case when t.occupied_through >= l.starts_on then t.occupied_through end as ends_on,
       t.recorded_at
from gba.property_leases l
cross join lateral (
    select 1 as revision, 'register'::text as action, l.agreement_revision,
           l.ends_on as occupied_through, l.recorded_at
    union all
    select e.revision, e.action, e.agreement_revision, e.occupied_through, e.recorded_at
    from gba.property_lease_term_events e where e.tenant_id = l.tenant_id and e.lease_id = l.id
) t
join gba.agreement_versions v on v.tenant_id = l.tenant_id and v.agreement_id = l.agreement_id
     and v.revision = t.agreement_revision
where l.tenant_id = %s and l.id = %s
"""


class LeaseTermInput(Versioned):
    action: Literal["extend", "release"]
    expected_revision: StrictInt = Field(ge=1, le=2_147_483_646)
    agreement_revision: StrictInt = Field(ge=1, le=2_147_483_647)


class LeaseTermView(Strict):
    schema_version: Literal[1] = 1
    lease_id: UUID
    revision: int
    action: Literal["register", "extend", "release"]
    agreement_revision: int
    document_id: UUID | None
    document_revision: int | None
    terminated_on: date | None
    starts_on: date
    ends_on: date | None
    recorded_at: AwareDatetime


class LeaseTermHistory(Strict):
    schema_version: Literal[1] = 1
    items: list[LeaseTermView]
    next_before: int | None


class LeaseTermReceipt(Strict):
    lease_id: UUID
    revision: int


class LeaseTermRevisionError(ConflictError):
    code = "PROPERTY_LEASE_REVISION_CONFLICT"


class LeaseReleasedError(ConflictError):
    code = "PROPERTY_LEASE_RELEASED"


class LeaseMoveInConflictError(ConflictError):
    code = "PROPERTY_LEASE_MOVE_IN_CONFLICT"


async def term_history(
    conn: RuntimeConnection, business: UUID, lease_id: UUID, before: int | None, limit: int
) -> LeaseTermHistory:
    async with conn.cursor(row_factory=class_row(LeaseTermView)) as cur:
        await cur.execute(
            f"{_SELECT} and (%s::integer is null or t.revision < %s)"
            " order by t.revision desc limit %s",
            (business, lease_id, before, before, limit + 1),
        )
        rows = await cur.fetchall()
    if not rows:
        await get_lease(conn, business, lease_id)
    items = rows[:limit]
    return LeaseTermHistory(
        items=items, next_before=items[-1].revision if len(rows) > limit else None
    )


async def _get_term(
    conn: RuntimeConnection, business: UUID, lease_id: UUID, revision: int
) -> LeaseTermView:
    async with conn.cursor(row_factory=class_row(LeaseTermView)) as cur:
        await cur.execute(f"{_SELECT} and t.revision = %s", (business, lease_id, revision))
        event = await cur.fetchone()
    if event is None:
        raise NotFoundError("Property lease term not found")
    return event


async def record_term(
    conn: RuntimeConnection,
    business: UUID,
    lease_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: LeaseTermInput,
) -> LeaseTermView:
    scope = IdempotencyScope(business, actor, "property.lease.term", key)
    fingerprint = commands.fingerprint({"lease_id": str(lease_id), **body.model_dump(mode="json")})
    receipt = await commands.claim(conn, scope, fingerprint, LeaseTermReceipt)
    if receipt is not None:
        return await _get_term(conn, business, receipt.lease_id, receipt.revision)
    if body.action == "extend":
        if not modules.MODULES_BY_ID[PROPERTY_MODULE].enableable:
            raise PropertyNotReadyError(
                "The property module is not ready", module_id=PROPERTY_MODULE
            )
        await require_module(conn, business, PROPERTY_MODULE)

    revision = body.expected_revision + 1
    try:
        async with module_writes(PROPERTY_MODULE):
            await conn.execute(
                "insert into gba.property_lease_term_events (tenant_id, lease_id, revision, "
                "action, agreement_revision, recorded_by) values (%s,%s,%s,%s,%s,%s)",
                (business, lease_id, revision, body.action, body.agreement_revision, user_id),
            )
    except errors.ExclusionViolation as exc:
        if exc.diag.constraint_name == "property_leases_no_overlap":
            raise LeaseOverlapError("A lease already covers these days for the unit") from exc
        raise
    except errors.CheckViolation as exc:
        match exc.diag.constraint_name:
            case "property_lease_term_lease":
                raise NotFoundError("Property lease not found") from exc
            case "property_lease_term_sequence":
                raise LeaseTermRevisionError("The lease term has changed") from exc
            case "property_lease_term_closed":
                raise LeaseReleasedError("The lease has already been released") from exc
            case "property_lease_term_move_in":
                raise LeaseMoveInConflictError(
                    "The term cannot end before a recorded move-in"
                ) from exc
            case "property_lease_term_source":
                raise InvalidReferenceError(
                    "Select the current agreement version for this term change",
                    field="agreement_revision",
                ) from exc
        raise

    await commands.audit(
        conn,
        business,
        actor,
        "property.lease_term_recorded",
        "property_lease",
        str(lease_id),
        {
            "action": body.action,
            "revision": revision,
            "agreement_revision": body.agreement_revision,
        },
    )
    await commands.complete(conn, scope, LeaseTermReceipt(lease_id=lease_id, revision=revision))
    return await _get_term(conn, business, lease_id, revision)
