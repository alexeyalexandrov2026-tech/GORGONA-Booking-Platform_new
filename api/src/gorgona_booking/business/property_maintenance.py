"""PROPERTY-01 5a: maintenance requests, lifecycle approvals and separate FIN-03 obligations."""

import re
from typing import Annotated, Literal
from uuid import UUID

from psycopg import errors
from psycopg.rows import class_row
from pydantic import AwareDatetime, Field, StrictInt, field_validator

from gorgona_booking.booking.idempotency import IdempotencyScope
from gorgona_booking.business import commands, modules
from gorgona_booking.business.contracts import Strict, Versioned
from gorgona_booking.business.module_gate import module_writes, require_module
from gorgona_booking.business.property_catalog import PROPERTY_MODULE, PropertyNotReadyError
from gorgona_booking.db.pool import RuntimeConnection
from gorgona_booking.errors import ConflictError, InvalidReferenceError, NotFoundError

Category = Literal["plumbing", "electrical", "hvac", "structural", "appliance", "general"]
Priority = Literal["emergency", "urgent", "routine"]
State = Literal["open", "approved", "assigned", "completed", "cancelled"]
Action = Literal["approve", "assign", "complete", "cancel"]

_MAX_REVISION = 2_147_483_647
_MAX_AMOUNT = 999_999_999_999
_PAGE_LIMIT = 50
_SINGLE_LINE_CTRL = re.compile(r"[\x00-\x1f\x7f]")
_MULTILINE_CTRL = re.compile(r"[\x00-\x08\x0b-\x1f\x7f]")


class MaintenanceRevisionError(ConflictError):
    code = "PROPERTY_MAINTENANCE_REVISION_CONFLICT"


class MaintenanceStateError(ConflictError):
    code = "PROPERTY_MAINTENANCE_STATE_INVALID"


class MaintenanceLimitError(ConflictError):
    code = "PROPERTY_MAINTENANCE_LIMIT_EXCEEDED"


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


class MaintenanceRequestInput(Versioned):
    object_id: UUID
    lease_id: UUID | None = None
    category: Category
    priority: Priority
    title: str
    description: str

    @field_validator("title")
    @classmethod
    def valid_title(cls, value: str) -> str:
        return _clean_single_line(value, 200)

    @field_validator("description")
    @classmethod
    def valid_description(cls, value: str) -> str:
        return _clean_multiline(value, 4000)


class _EventBase(Versioned):
    expected_revision: StrictInt = Field(ge=1, le=_MAX_REVISION - 1)
    note: str | None = None

    @field_validator("note")
    @classmethod
    def valid_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_multiline(value, 2000)


class ApproveMaintenanceInput(_EventBase):
    action: Literal["approve"]
    approved_limit_minor: StrictInt = Field(ge=1, le=_MAX_AMOUNT)
    currency: str = Field(pattern=r"^[A-Z]{3}$")


class AssignMaintenanceInput(_EventBase):
    action: Literal["assign"]
    contractor_id: UUID


class CompleteMaintenanceInput(_EventBase):
    action: Literal["complete"]


class CancelMaintenanceInput(_EventBase):
    action: Literal["cancel"]


MaintenanceEventInput = Annotated[
    ApproveMaintenanceInput
    | AssignMaintenanceInput
    | CompleteMaintenanceInput
    | CancelMaintenanceInput,
    Field(discriminator="action"),
]


class MaintenanceObligationInput(Versioned):
    book_id: UUID
    invoice_document_id: UUID
    note: str | None = None

    @field_validator("note")
    @classmethod
    def valid_note(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return _clean_multiline(value, 500)


class MaintenanceRequestView(Strict):
    schema_version: Literal[1] = 1
    request_id: UUID
    object_id: UUID
    location_id: UUID
    object_kind: str
    lease_id: UUID | None
    category: Category
    priority: Priority
    title: str
    description: str
    revision: int
    state: State
    approved_limit_minor: int | None
    currency: str | None
    contractor_id: UUID | None
    recorded_by: UUID
    recorded_at: AwareDatetime


class MaintenanceRequestList(Strict):
    schema_version: Literal[1] = 1
    items: list[MaintenanceRequestView]
    next_after: UUID | None = None


class MaintenanceEventView(Strict):
    schema_version: Literal[1] = 1
    request_id: UUID
    revision: int
    action: Action
    approved_limit_minor: int | None
    currency: str | None
    contractor_id: UUID | None
    note: str | None
    recorded_by: UUID
    recorded_at: AwareDatetime


class MaintenanceEventHistory(Strict):
    schema_version: Literal[1] = 1
    items: list[MaintenanceEventView]
    next_before: int | None = None


class MaintenanceObligationView(Strict):
    schema_version: Literal[1] = 1
    request_id: UUID
    number: int
    book_id: UUID
    invoice_document_id: UUID
    obligation_id: UUID
    amount_minor: int
    currency: str
    note: str | None
    recorded_by: UUID
    recorded_at: AwareDatetime


class MaintenanceObligationList(Strict):
    schema_version: Literal[1] = 1
    items: list[MaintenanceObligationView]


class _RequestReceipt(Strict):
    request_id: UUID


class _EventReceipt(Strict):
    request_id: UUID
    revision: int


class _ObligationReceipt(Strict):
    request_id: UUID
    number: int


_SELECT_REQUEST = """
select r.id as request_id, r.object_id, r.location_id, r.object_kind, r.lease_id,
       r.category, r.priority, r.title, r.description, r.revision, r.state,
       r.approved_limit_minor, r.currency, r.contractor_id, r.recorded_by, r.recorded_at
from gba.property_maintenance_requests r
"""


async def get_request(
    conn: RuntimeConnection, business: UUID, request_id: UUID
) -> MaintenanceRequestView:
    async with conn.cursor(row_factory=class_row(MaintenanceRequestView)) as cur:
        await cur.execute(
            f"{_SELECT_REQUEST} where r.tenant_id = %s and r.id = %s",
            (business, request_id),
        )
        found = await cur.fetchone()
    if found is None:
        raise NotFoundError("Property maintenance request not found")
    return found


async def list_requests(
    conn: RuntimeConnection,
    business: UUID,
    *,
    after: UUID | None,
    object_id: UUID | None,
    limit: int = _PAGE_LIMIT,
) -> MaintenanceRequestList:
    async with conn.cursor(row_factory=class_row(MaintenanceRequestView)) as cur:
        await cur.execute(
            f"{_SELECT_REQUEST} "
            "where r.tenant_id = %s "
            "  and (%s::uuid is null or r.object_id = %s) "
            "  and (%s::uuid is null or r.id > %s) "
            "order by r.id limit %s",
            (business, object_id, object_id, after, after, limit + 1),
        )
        rows = await cur.fetchall()
    has_more = len(rows) > limit
    items = rows[:limit]
    return MaintenanceRequestList(
        items=items, next_after=items[-1].request_id if has_more else None
    )


async def create_request(
    conn: RuntimeConnection,
    business: UUID,
    request_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: MaintenanceRequestInput,
) -> MaintenanceRequestView:
    scope = IdempotencyScope(business, actor, "property.maintenance.create", key)
    fingerprint = commands.fingerprint(
        {"request_id": str(request_id), **body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _RequestReceipt)
    if receipt is not None:
        return await get_request(conn, business, receipt.request_id)
    if not modules.MODULES_BY_ID[PROPERTY_MODULE].enableable:
        raise PropertyNotReadyError("The property module is not ready", module_id=PROPERTY_MODULE)
    await require_module(conn, business, PROPERTY_MODULE)

    try:
        async with module_writes(PROPERTY_MODULE):
            await conn.execute(
                "insert into gba.property_maintenance_requests "
                "(tenant_id, id, object_id, lease_id, category, priority, "
                "title, description, recorded_by) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    business,
                    request_id,
                    body.object_id,
                    body.lease_id,
                    body.category,
                    body.priority,
                    body.title,
                    body.description,
                    user_id,
                ),
            )
    except errors.UniqueViolation as exc:
        if exc.diag.constraint_name == "property_maintenance_requests_pkey":
            raise ConflictError("This maintenance request already exists") from exc
        raise
    except errors.ForeignKeyViolation as exc:
        if exc.diag.constraint_name == "property_maintenance_requests_lease_fk":
            raise InvalidReferenceError(
                "Select a recorded property lease", field="lease_id"
            ) from exc
        raise
    except errors.CheckViolation as exc:
        match exc.diag.constraint_name:
            case "property_maintenance_request_object":
                raise InvalidReferenceError(
                    "Select an existing property object", field="object_id"
                ) from exc
            case "property_maintenance_request_lease":
                raise InvalidReferenceError(
                    "Select a lease for the same property object", field="lease_id"
                ) from exc
        raise

    await commands.audit(
        conn,
        business,
        actor,
        "property.maintenance_request_created",
        "property_maintenance_request",
        str(request_id),
        {"object_id": str(body.object_id), "category": body.category, "priority": body.priority},
    )
    await commands.complete(conn, scope, _RequestReceipt(request_id=request_id))
    return await get_request(conn, business, request_id)


async def list_events(
    conn: RuntimeConnection,
    business: UUID,
    request_id: UUID,
    *,
    before: int | None,
    limit: int,
) -> MaintenanceEventHistory:
    await get_request(conn, business, request_id)
    async with conn.cursor(row_factory=class_row(MaintenanceEventView)) as cur:
        await cur.execute(
            "select e.request_id, e.revision, e.action, e.approved_limit_minor, e.currency, "
            "       e.contractor_id, e.note, e.recorded_by, e.recorded_at "
            "from gba.property_maintenance_events e "
            "where e.tenant_id = %s and e.request_id = %s "
            "  and (%s::integer is null or e.revision < %s) "
            "order by e.revision desc limit %s",
            (business, request_id, before, before, limit + 1),
        )
        rows = await cur.fetchall()
    has_more = len(rows) > limit
    items = rows[:limit]
    return MaintenanceEventHistory(
        items=items, next_before=items[-1].revision if has_more else None
    )


async def record_event(
    conn: RuntimeConnection,
    business: UUID,
    request_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: MaintenanceEventInput,
) -> MaintenanceRequestView:
    scope = IdempotencyScope(business, actor, "property.maintenance.event", key)
    fingerprint = commands.fingerprint(
        {"request_id": str(request_id), **body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _EventReceipt)
    if receipt is not None:
        return await get_request(conn, business, receipt.request_id)

    if body.action in ("approve", "assign"):
        if not modules.MODULES_BY_ID[PROPERTY_MODULE].enableable:
            raise PropertyNotReadyError(
                "The property module is not ready", module_id=PROPERTY_MODULE
            )
        await require_module(conn, business, PROPERTY_MODULE)

    next_revision = body.expected_revision + 1
    approved_limit = (
        body.approved_limit_minor if isinstance(body, ApproveMaintenanceInput) else None
    )
    currency = body.currency if isinstance(body, ApproveMaintenanceInput) else None
    contractor_id = body.contractor_id if isinstance(body, AssignMaintenanceInput) else None

    try:
        async with module_writes(PROPERTY_MODULE):
            await conn.execute(
                "insert into gba.property_maintenance_events "
                "(tenant_id, request_id, revision, action, approved_limit_minor, currency, "
                " contractor_id, note, recorded_by) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    business,
                    request_id,
                    next_revision,
                    body.action,
                    approved_limit,
                    currency,
                    contractor_id,
                    body.note,
                    user_id,
                ),
            )
    except errors.UniqueViolation as exc:
        if exc.diag.constraint_name == "property_maintenance_events_pkey":
            raise MaintenanceRevisionError("The maintenance request has changed") from exc
        raise
    except errors.ForeignKeyViolation as exc:
        match exc.diag.constraint_name:
            case "property_maintenance_events_contractor_fk":
                raise InvalidReferenceError(
                    "Select an existing contractor counterparty", field="contractor_id"
                ) from exc
            case "property_maintenance_events_currency_fkey":
                raise InvalidReferenceError(
                    "Select a supported currency", field="currency"
                ) from exc
        raise
    except errors.CheckViolation as exc:
        match exc.diag.constraint_name:
            case "property_maintenance_event_request":
                raise NotFoundError("Property maintenance request not found") from exc
            case "property_maintenance_event_sequence":
                raise MaintenanceRevisionError("The maintenance request has changed") from exc
            case (
                "property_maintenance_event_state"
                | "property_maintenance_assign_has_obligations"
                | "property_maintenance_cancel_has_obligations"
            ):
                raise MaintenanceStateError(exc.diag.message_primary or "Invalid state") from exc
        raise

    await commands.audit(
        conn,
        business,
        actor,
        f"property.maintenance_{body.action}",
        "property_maintenance_request",
        str(request_id),
        {"revision": next_revision, "action": body.action},
    )
    await commands.complete(
        conn, scope, _EventReceipt(request_id=request_id, revision=next_revision)
    )
    return await get_request(conn, business, request_id)


async def list_obligations(
    conn: RuntimeConnection, business: UUID, request_id: UUID
) -> MaintenanceObligationList:
    await get_request(conn, business, request_id)
    async with conn.cursor(row_factory=class_row(MaintenanceObligationView)) as cur:
        await cur.execute(
            "select o.request_id, o.number, o.book_id, o.invoice_document_id, o.obligation_id, "
            "       o.amount_minor, o.currency, o.note, o.recorded_by, o.recorded_at "
            "from gba.property_maintenance_obligations o "
            "where o.tenant_id = %s and o.request_id = %s order by o.number asc",
            (business, request_id),
        )
        items = await cur.fetchall()
    return MaintenanceObligationList(items=items)


async def _get_obligation(
    conn: RuntimeConnection, business: UUID, request_id: UUID, number: int
) -> MaintenanceObligationView:
    async with conn.cursor(row_factory=class_row(MaintenanceObligationView)) as cur:
        await cur.execute(
            "select o.request_id, o.number, o.book_id, o.invoice_document_id, o.obligation_id, "
            "       o.amount_minor, o.currency, o.note, o.recorded_by, o.recorded_at "
            "from gba.property_maintenance_obligations o "
            "where o.tenant_id = %s and o.request_id = %s and o.number = %s",
            (business, request_id, number),
        )
        found = await cur.fetchone()
    if found is None:
        raise NotFoundError("Property maintenance obligation not found")
    return found


async def record_obligation(
    conn: RuntimeConnection,
    business: UUID,
    request_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: MaintenanceObligationInput,
) -> MaintenanceObligationView:
    scope = IdempotencyScope(business, actor, "property.maintenance.obligation", key)
    fingerprint = commands.fingerprint(
        {"request_id": str(request_id), **body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _ObligationReceipt)
    if receipt is not None:
        return await _get_obligation(conn, business, receipt.request_id, receipt.number)
    if not modules.MODULES_BY_ID[PROPERTY_MODULE].enableable:
        raise PropertyNotReadyError("The property module is not ready", module_id=PROPERTY_MODULE)
    await require_module(conn, business, PROPERTY_MODULE)

    row = await (
        await conn.execute(
            "select object_id from gba.property_maintenance_requests "
            "where tenant_id = %s and id = %s",
            (business, request_id),
        )
    ).fetchone()
    if row is None:
        raise NotFoundError("Property maintenance request not found")

    await conn.execute("select gba.lock_property_object(%s, %s)", (business, row[0]))
    seq_row = await (
        await conn.execute(
            "select coalesce(max(number), 0) + 1 from gba.property_maintenance_obligations "
            "where tenant_id = %s and request_id = %s",
            (business, request_id),
        )
    ).fetchone()
    number = int(seq_row[0]) if seq_row is not None else 1

    try:
        async with module_writes(PROPERTY_MODULE):
            await conn.execute(
                "insert into gba.property_maintenance_obligations "
                "(tenant_id, request_id, number, book_id, invoice_document_id, note, recorded_by) "
                "values (%s,%s,%s,%s,%s,%s,%s)",
                (
                    business,
                    request_id,
                    number,
                    body.book_id,
                    body.invoice_document_id,
                    body.note,
                    user_id,
                ),
            )
    except errors.UniqueViolation as exc:
        if exc.diag.constraint_name in (
            "property_maintenance_obligations_unique_invoice",
            "property_maintenance_obligations_unique_obligation",
        ):
            raise ConflictError("This invoice is already linked to a maintenance request") from exc
        raise
    except errors.ForeignKeyViolation as exc:
        if exc.diag.constraint_name == "property_maintenance_obligations_document_fk":
            raise InvalidReferenceError(
                "Select an issued payable invoice", field="invoice_document_id"
            ) from exc
        raise
    except errors.CheckViolation as exc:
        match exc.diag.constraint_name:
            case "property_maintenance_obligation_request":
                raise NotFoundError("Property maintenance request not found") from exc
            case "property_maintenance_obligation_state":
                raise MaintenanceStateError(
                    "Assign a contractor to an approved request before linking obligations"
                ) from exc
            case "property_maintenance_obligation_document":
                raise InvalidReferenceError(
                    "Select an issued payable invoice for the assigned contractor "
                    "in the approved currency",
                    field="invoice_document_id",
                ) from exc
            case "property_maintenance_obligation_limit":
                raise MaintenanceLimitError(
                    "Linked obligations exceed the approved maintenance limit"
                ) from exc
        raise

    linked = await _get_obligation(conn, business, request_id, number)
    await commands.audit(
        conn,
        business,
        actor,
        "property.maintenance_obligation_linked",
        "property_maintenance_request",
        str(request_id),
        {
            "number": number,
            "book_id": str(body.book_id),
            "invoice_document_id": str(body.invoice_document_id),
            "obligation_id": str(linked.obligation_id),
            "amount_minor": linked.amount_minor,
            "currency": linked.currency,
        },
    )
    await commands.complete(conn, scope, _ObligationReceipt(request_id=request_id, number=number))
    return linked
