"""Company-wide registrations of signed exclusive unit leases."""

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
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError

PAGE = 50
_SELECT = (
    "select l.id as lease_id, l.object_id, l.agreement_id, l.agreement_revision, "
    "v.document_id, v.document_revision, v.signed_on, l.starts_on, l.ends_on, l.recorded_at "
    "from gba.property_leases l join gba.agreement_versions v "
    "on v.tenant_id = l.tenant_id and v.agreement_id = l.agreement_id "
    "and v.revision = l.agreement_revision "
)


class LeaseInput(Versioned):
    object_id: UUID
    agreement_id: UUID
    agreement_revision: StrictInt = Field(ge=1, le=2_147_483_647)


class LeaseView(Strict):
    schema_version: Literal[1] = 1
    lease_id: UUID
    object_id: UUID
    agreement_id: UUID
    agreement_revision: int
    document_id: UUID
    document_revision: int
    signed_on: date
    starts_on: date
    ends_on: date
    recorded_at: AwareDatetime


class LeaseList(Strict):
    schema_version: Literal[1] = 1
    items: list[LeaseView]
    next_cursor: UUID | None


class LeaseReceipt(Strict):
    lease_id: UUID


class LeaseOverlapError(ConflictError):
    code = "PROPERTY_LEASE_OVERLAP"


async def list_leases(
    conn: RuntimeConnection,
    business: UUID,
    after: UUID | None,
    object_id: UUID | None = None,
) -> LeaseList:
    """Page company leases. An object id limits the page to that unit and keeps cursor order."""
    async with conn.cursor(row_factory=class_row(LeaseView)) as cur:
        await cur.execute(
            f"{_SELECT} where l.tenant_id = %s and (%s::uuid is null or l.object_id = %s)"
            " and (%s::uuid is null or l.id > %s) order by l.id limit %s",
            (business, object_id, object_id, after, after, PAGE + 1),
        )
        rows = await cur.fetchall()
    items = rows[:PAGE]
    return LeaseList(items=items, next_cursor=items[-1].lease_id if len(rows) > PAGE else None)


async def get_lease(conn: RuntimeConnection, business: UUID, lease_id: UUID) -> LeaseView:
    async with conn.cursor(row_factory=class_row(LeaseView)) as cur:
        await cur.execute(f"{_SELECT} where l.tenant_id = %s and l.id = %s", (business, lease_id))
        lease = await cur.fetchone()
    if lease is None:
        raise NotFoundError("Property lease not found")
    return lease


async def register_lease(
    conn: RuntimeConnection,
    business: UUID,
    lease_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: LeaseInput,
) -> LeaseView:
    scope = IdempotencyScope(business, actor, "property.lease.register", key)
    fingerprint = commands.fingerprint({"lease_id": str(lease_id), **body.model_dump(mode="json")})
    receipt = await commands.claim(conn, scope, fingerprint, LeaseReceipt)
    if receipt is not None:
        return await get_lease(conn, business, receipt.lease_id)
    if not modules.MODULES_BY_ID[PROPERTY_MODULE].enableable:
        raise PropertyNotReadyError("The property module is not ready", module_id=PROPERTY_MODULE)
    await require_module(conn, business, PROPERTY_MODULE)

    try:
        async with module_writes(PROPERTY_MODULE):
            await conn.execute(
                "insert into gba.property_leases (tenant_id, id, object_id, agreement_id, "
                "agreement_revision, recorded_by) values (%s,%s,%s,%s,%s,%s)",
                (
                    business,
                    lease_id,
                    body.object_id,
                    body.agreement_id,
                    body.agreement_revision,
                    user_id,
                ),
            )
    except errors.ExclusionViolation as exc:
        if exc.diag.constraint_name == "property_leases_no_overlap":
            raise LeaseOverlapError("A lease already covers these days for the unit") from exc
        raise
    except errors.UniqueViolation as exc:
        if exc.diag.constraint_name in ("property_leases_pkey", "property_leases_one_registration"):
            raise ConflictError("This lease ID or agreement is already registered") from exc
        raise
    except errors.CheckViolation as exc:
        if exc.diag.constraint_name == "property_leases_unit":
            raise InvalidReferenceError("Select a property unit", field="object_id") from exc
        if exc.diag.constraint_name == "property_leases_signed_source":
            raise InvalidReferenceError(
                "Select a current signed version with a stored file and both term dates",
                field="agreement_id",
            ) from exc
        raise

    await commands.audit(
        conn,
        business,
        actor,
        "property.lease_registered",
        "property_lease",
        str(lease_id),
        {"object_id": str(body.object_id), "agreement_revision": body.agreement_revision},
    )
    await commands.complete(conn, scope, LeaseReceipt(lease_id=lease_id))
    return await get_lease(conn, business, lease_id)
