"""Record a unit move-in and its private condition documents."""

from datetime import date
from typing import Literal, Self
from uuid import UUID

from psycopg import errors
from psycopg.rows import class_row
from pydantic import AwareDatetime, Field, StrictInt, model_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, modules
from gorgona_booking.business.agreement_contracts import DocumentReference
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.property_catalog import PROPERTY_MODULE, PropertyNotReadyError
from gorgona_booking.business.property_lease_terms import LeaseTermRevisionError
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError

_SELECT = """
select m.lease_id, m.term_revision, m.moved_in_on,
       jsonb_build_object('document_id', m.report_id, 'revision', m.report_revision) as report,
       (select jsonb_agg(jsonb_build_object(
           'document_id', p.document_id, 'revision', p.document_revision) order by p.position)
        from gba.property_move_in_photos p
        where p.tenant_id = m.tenant_id and p.lease_id = m.lease_id) as photos,
       m.recorded_by, m.recorded_at
from gba.property_move_ins m where m.tenant_id = %s and m.lease_id = %s
"""


class MoveInInput(Versioned):
    term_revision: StrictInt = Field(ge=1, le=2_147_483_647)
    moved_in_on: date
    report: DocumentReference
    photos: tuple[DocumentReference, ...] = Field(min_length=1, max_length=50)

    @model_validator(mode="after")
    def unique_photos(self) -> Self:
        if len(set(self.photos)) != len(self.photos):
            raise ValueError("Select each photo version once")
        return self


class MoveInView(Strict):
    schema_version: Literal[1] = 1
    lease_id: UUID
    term_revision: int
    moved_in_on: date
    report: DocumentReference
    photos: list[DocumentReference]
    recorded_by: UUID
    recorded_at: AwareDatetime


class MoveInReceipt(Strict):
    lease_id: UUID


async def get_move_in(conn: RuntimeConnection, business: UUID, lease_id: UUID) -> MoveInView:
    async with conn.cursor(row_factory=class_row(MoveInView)) as cur:
        await cur.execute(_SELECT, (business, lease_id))
        move_in = await cur.fetchone()
    if move_in is None:
        raise NotFoundError("Property move-in not found")
    return move_in


async def record_move_in(
    conn: RuntimeConnection,
    business: UUID,
    lease_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: MoveInInput,
) -> MoveInView:
    scope = IdempotencyScope(business, actor, "property.lease.move_in", key)
    fingerprint = commands.fingerprint({"lease_id": str(lease_id), **body.model_dump(mode="json")})
    receipt = await commands.claim(conn, scope, fingerprint, MoveInReceipt)
    if receipt is not None:
        return await get_move_in(conn, business, receipt.lease_id)
    if not modules.MODULES_BY_ID[PROPERTY_MODULE].enableable:
        raise PropertyNotReadyError("The property module is not ready", module_id=PROPERTY_MODULE)
    await require_module(conn, business, PROPERTY_MODULE)

    try:
        async with module_writes(PROPERTY_MODULE):
            await conn.execute(
                "insert into gba.property_move_ins (tenant_id, lease_id, term_revision, "
                "moved_in_on, report_id, report_revision, photo_count, recorded_by) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    business,
                    lease_id,
                    body.term_revision,
                    body.moved_in_on,
                    body.report.document_id,
                    body.report.revision,
                    len(body.photos),
                    user_id,
                ),
            )
            async with conn.cursor() as cur:
                await cur.executemany(
                    "insert into gba.property_move_in_photos "
                    "(tenant_id, lease_id, position, document_id, document_revision) "
                    "values (%s,%s,%s,%s,%s)",
                    (
                        (business, lease_id, position, photo.document_id, photo.revision)
                        for position, photo in enumerate(body.photos, start=1)
                    ),
                )
    except errors.UniqueViolation as exc:
        if exc.diag.constraint_name == "property_move_ins_pkey":
            raise ConflictError("This lease already has a move-in report") from exc
        raise
    except errors.CheckViolation as exc:
        match exc.diag.constraint_name:
            case "property_move_in_lease":
                raise NotFoundError("Property lease not found") from exc
            case "property_move_in_revision":
                raise LeaseTermRevisionError("The lease term has changed") from exc
            case "property_move_in_day":
                raise InvalidReferenceError(
                    "Select a day within the current term up to today", field="moved_in_on"
                ) from exc
            case "property_move_in_report":
                raise InvalidReferenceError(
                    "Select a stored condition report", field="report"
                ) from exc
            case "property_move_in_photo":
                raise InvalidReferenceError(
                    "Select stored JPEG or PNG photos", field="photos"
                ) from exc
        raise

    await commands.audit(
        conn,
        business,
        actor,
        "property.lease_move_in_recorded",
        "property_lease",
        str(lease_id),
        {"term_revision": body.term_revision, "photo_count": len(body.photos)},
    )
    await commands.complete(conn, scope, MoveInReceipt(lease_id=lease_id))
    return await get_move_in(conn, business, lease_id)
