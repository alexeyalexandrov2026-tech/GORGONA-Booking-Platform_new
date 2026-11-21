"""PROPERTY-01 6a: record a unit move-out condition report and its photos."""

import re
from datetime import date
from typing import Literal, Self
from uuid import UUID

from psycopg import errors
from psycopg.rows import class_row
from pydantic import AwareDatetime, Field, StrictInt, field_validator, model_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, modules
from gorgona_booking.business.agreement_contracts import DocumentReference
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.property_catalog import PROPERTY_MODULE, PropertyNotReadyError
from gorgona_booking.business.property_lease_terms import LeaseTermRevisionError
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError

ConditionSummary = Literal["normal_wear", "damage_noted"]
_MULTILINE_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")

_SELECT = """
select m.lease_id, m.term_revision, m.moved_out_on, m.condition_summary, m.note,
       jsonb_build_object('document_id', m.report_id, 'revision', m.report_revision) as report,
       (select jsonb_agg(jsonb_build_object(
           'document_id', p.document_id, 'revision', p.document_revision) order by p.position)
        from gba.property_move_out_photos p
        where p.tenant_id = m.tenant_id and p.lease_id = m.lease_id) as photos,
       m.recorded_by, m.recorded_at
from gba.property_move_outs m where m.tenant_id = %s and m.lease_id = %s
"""


class MoveOutRequiresMoveInError(ConflictError):
    code = "PROPERTY_MOVE_OUT_REQUIRES_MOVE_IN"


class MoveOutInput(Versioned):
    term_revision: StrictInt = Field(ge=1, le=2_147_483_647)
    moved_out_on: date
    condition_summary: ConditionSummary
    note: str | None = None
    report: DocumentReference
    photos: tuple[DocumentReference, ...] = Field(min_length=1, max_length=50)

    @field_validator("note")
    @classmethod
    def valid_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if _MULTILINE_CTRL.search(value):
            raise ValueError("Control characters are not allowed")
        cleaned = value.strip()
        if not cleaned or len(cleaned) > 2000:
            raise ValueError("Enter between 1 and 2000 characters")
        return cleaned

    @model_validator(mode="after")
    def unique_photos(self) -> Self:
        if len(set(self.photos)) != len(self.photos):
            raise ValueError("Select each photo version once")
        return self


class MoveOutView(Strict):
    schema_version: Literal[1] = 1
    lease_id: UUID
    term_revision: int
    moved_out_on: date
    condition_summary: ConditionSummary
    note: str | None
    report: DocumentReference
    photos: list[DocumentReference]
    recorded_by: UUID
    recorded_at: AwareDatetime


class MoveOutReceipt(Strict):
    lease_id: UUID


async def get_move_out(conn: RuntimeConnection, business: UUID, lease_id: UUID) -> MoveOutView:
    async with conn.cursor(row_factory=class_row(MoveOutView)) as cur:
        await cur.execute(_SELECT, (business, lease_id))
        found = await cur.fetchone()
    if found is None:
        raise NotFoundError("Property move-out not found")
    return found


async def record_move_out(
    conn: RuntimeConnection,
    business: UUID,
    lease_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: MoveOutInput,
) -> MoveOutView:
    scope = IdempotencyScope(business, actor, "property.lease.move_out", key)
    fingerprint = commands.fingerprint({"lease_id": str(lease_id), **body.model_dump(mode="json")})
    receipt = await commands.claim(conn, scope, fingerprint, MoveOutReceipt)
    if receipt is not None:
        return await get_move_out(conn, business, receipt.lease_id)
    if not modules.MODULES_BY_ID[PROPERTY_MODULE].enableable:
        raise PropertyNotReadyError("The property module is not ready", module_id=PROPERTY_MODULE)
    await require_module(conn, business, PROPERTY_MODULE)

    try:
        async with module_writes(PROPERTY_MODULE):
            await conn.execute(
                "insert into gba.property_move_outs "
                "(tenant_id, lease_id, term_revision, moved_out_on, condition_summary, note, "
                " report_id, report_revision, photo_count, recorded_by) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    business,
                    lease_id,
                    body.term_revision,
                    body.moved_out_on,
                    body.condition_summary,
                    body.note,
                    body.report.document_id,
                    body.report.revision,
                    len(body.photos),
                    user_id,
                ),
            )
            async with conn.cursor() as cur:
                await cur.executemany(
                    "insert into gba.property_move_out_photos "
                    "(tenant_id, lease_id, position, document_id, document_revision) "
                    "values (%s,%s,%s,%s,%s)",
                    (
                        (business, lease_id, position, photo.document_id, photo.revision)
                        for position, photo in enumerate(body.photos, start=1)
                    ),
                )
    except errors.UniqueViolation as exc:
        if exc.diag.constraint_name == "property_move_outs_pkey":
            raise ConflictError("This lease already has a move-out report") from exc
        raise
    except errors.CheckViolation as exc:
        match exc.diag.constraint_name:
            case "property_move_out_lease":
                raise NotFoundError("Property lease not found") from exc
            case "property_move_out_requires_move_in":
                raise MoveOutRequiresMoveInError(
                    "Record a move-in before recording move-out"
                ) from exc
            case "property_move_out_revision":
                raise LeaseTermRevisionError("The lease term has changed") from exc
            case "property_move_out_day":
                raise InvalidReferenceError(
                    "Select a day from move-in through the current term up to today",
                    field="moved_out_on",
                ) from exc
            case "property_move_out_report_distinct":
                raise InvalidReferenceError(
                    "Select a move-out report different from the move-in report", field="report"
                ) from exc
            case "property_move_out_report":
                raise InvalidReferenceError(
                    "Select a stored condition report", field="report"
                ) from exc
            case "property_move_out_photo":
                raise InvalidReferenceError(
                    "Select stored JPEG or PNG photos", field="photos"
                ) from exc
        raise

    await commands.audit(
        conn,
        business,
        actor,
        "property.lease_move_out_recorded",
        "property_lease",
        str(lease_id),
        {
            "term_revision": body.term_revision,
            "condition_summary": body.condition_summary,
            "photo_count": len(body.photos),
        },
    )
    await commands.complete(conn, scope, MoveOutReceipt(lease_id=lease_id))
    return await get_move_out(conn, business, lease_id)
