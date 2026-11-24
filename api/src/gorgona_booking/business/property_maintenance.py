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
from gorgona_booking.errors import (
    ConflictError,
    InvalidReferenceError,
    NotFoundError,
)
from gorgona_booking.tenancy.authorization import DelegationScope, PermissionDeniedError

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


ContractorUpdateKind = Literal["acknowledged", "in_progress", "parts_needed", "work_done"]


class ContractorCompanyInput(Versioned):
    expected_revision: StrictInt = Field(ge=0, le=_MAX_REVISION - 1)
    company_id: UUID | None = None


class ContractorCompanyView(Strict):
    schema_version: Literal[1] = 1
    request_id: UUID
    revision: int
    contractor_id: UUID | None
    company_id: UUID | None
    created_by: UUID | None
    created_at: AwareDatetime | None


class ContractorUpdateInput(Versioned):
    kind: ContractorUpdateKind
    note: str

    @field_validator("note")
    @classmethod
    def valid_note(cls, value: str) -> str:
        return _clean_multiline(value, 2000)


class ContractorUpdateView(Strict):
    schema_version: Literal[1] = 1
    request_id: UUID
    number: int
    kind: ContractorUpdateKind
    note: str
    company_id: UUID
    company_name: str
    grant_id: UUID
    binding_revision: int
    recorded_by: UUID
    created_at: AwareDatetime


class ContractorUpdateList(Strict):
    schema_version: Literal[1] = 1
    items: list[ContractorUpdateView]


class ContractorWorkOrderView(Strict):
    """Strict single-assignment contractor view; excludes lease, budget, obligations and parties."""

    schema_version: Literal[1] = 1
    request_id: UUID
    object_id: UUID
    object_name: str
    object_kind: str
    location_id: UUID
    category: Category
    priority: Priority
    title: str
    description: str
    state: State
    revision: int
    binding_revision: int
    contractor_company_id: UUID
    updates: list[ContractorUpdateView]


class _ContractorLinkReceipt(Strict):
    request_id: UUID
    revision: int


class _ContractorUpdateReceipt(Strict):
    request_id: UUID
    number: int


async def get_contractor_company(
    conn: RuntimeConnection, business: UUID, request_id: UUID
) -> ContractorCompanyView:
    req = await get_request(conn, business, request_id)
    row = await (
        await conn.execute(
            "select revision, contractor_id, company_id, created_by, created_at "
            "from gba.property_maintenance_contractor_links "
            "where tenant_id = %s and request_id = %s order by revision desc limit 1",
            (business, request_id),
        )
    ).fetchone()
    if row is None:
        return ContractorCompanyView(
            request_id=request_id,
            revision=0,
            contractor_id=req.contractor_id,
            company_id=None,
            created_by=None,
            created_at=None,
        )
    return ContractorCompanyView(
        request_id=request_id,
        revision=row[0],
        contractor_id=row[1],
        company_id=row[2],
        created_by=row[3],
        created_at=row[4],
    )


async def set_contractor_company(
    conn: RuntimeConnection,
    business: UUID,
    request_id: UUID,
    *,
    user_id: UUID,
    actor: str,
    key: str,
    body: ContractorCompanyInput,
) -> ContractorCompanyView:
    scope = IdempotencyScope(business, actor, "property.maintenance.contractor_company", key)
    fingerprint = commands.fingerprint(
        {"request_id": str(request_id), **body.model_dump(mode="json")}
    )
    receipt = await commands.claim(conn, scope, fingerprint, _ContractorLinkReceipt)
    if receipt is not None:
        return await get_contractor_company(conn, business, receipt.request_id)
    if not modules.MODULES_BY_ID[PROPERTY_MODULE].enableable:
        raise PropertyNotReadyError("The property module is not ready", module_id=PROPERTY_MODULE)
    await require_module(conn, business, PROPERTY_MODULE)

    req = await get_request(conn, business, request_id)
    if req.state != "assigned" or req.contractor_id is None:
        raise MaintenanceStateError(
            "Assign a contractor before binding a contractor company to this request"
        )
    next_rev = body.expected_revision + 1
    try:
        async with module_writes(PROPERTY_MODULE):
            await conn.execute(
                "insert into gba.property_maintenance_contractor_links "
                "(tenant_id, request_id, revision, contractor_id, company_id, created_by) "
                "values (%s,%s,%s,%s,%s,%s)",
                (business, request_id, next_rev, req.contractor_id, body.company_id, user_id),
            )
    except errors.UniqueViolation as exc:
        if exc.diag.constraint_name == "property_maintenance_contractor_links_pkey":
            raise MaintenanceRevisionError("The contractor company binding has changed") from exc
        raise
    except errors.ForeignKeyViolation as exc:
        if exc.diag.constraint_name == "property_maintenance_contractor_link_recipient":
            raise InvalidReferenceError(
                "Select an existing contractor business", field="company_id"
            ) from exc
        raise
    except errors.CheckViolation as exc:
        match exc.diag.constraint_name:
            case "property_maintenance_contractor_link_separate":
                raise InvalidReferenceError(
                    "Contractor company must be a different business", field="company_id"
                ) from exc
            case "property_maintenance_contractor_link_revision":
                raise MaintenanceRevisionError(
                    "The contractor company binding has changed"
                ) from exc
            case "property_maintenance_contractor_link_request":
                raise MaintenanceStateError(
                    "Assign a contractor before binding a contractor company to this request"
                ) from exc
        raise

    await commands.audit(
        conn,
        business,
        actor,
        "property.maintenance_contractor_company_bound",
        "property_maintenance_request",
        str(request_id),
        {"revision": next_rev, "company_id": str(body.company_id) if body.company_id else None},
    )
    await commands.complete(
        conn, scope, _ContractorLinkReceipt(request_id=request_id, revision=next_rev)
    )
    return await get_contractor_company(conn, business, request_id)


async def list_contractor_updates(
    conn: RuntimeConnection, business: UUID, request_id: UUID
) -> ContractorUpdateList:
    await get_request(conn, business, request_id)
    items = await _load_contractor_updates(conn, business, request_id)
    return ContractorUpdateList(items=items)


async def _load_contractor_updates(
    conn: RuntimeConnection, business: UUID, request_id: UUID
) -> list[ContractorUpdateView]:
    async with conn.cursor(row_factory=class_row(ContractorUpdateView)) as cur:
        await cur.execute(
            "select u.request_id, u.number, u.kind, u.note, u.company_id, "
            "       g.servicer_display_name as company_name, u.grant_id, "
            "       u.binding_revision, u.recorded_by, u.created_at "
            "from gba.property_maintenance_contractor_updates u "
            "join gba.delegation_grants g "
            "  on (g.owner_tenant_id, g.id, g.servicer_tenant_id) "
            "   = (u.tenant_id, u.grant_id, u.company_id) "
            "where u.tenant_id = %s and u.request_id = %s order by u.number asc",
            (business, request_id),
        )
        return await cur.fetchall()


async def _require_contractor_binding(
    conn: RuntimeConnection,
    business: UUID,
    request_id: UUID,
    delegation: DelegationScope,
    location_id: UUID | None,
) -> tuple[MaintenanceRequestView, int, str]:
    """Verify single-assignment binding before any contractor read, write or replay."""
    row = await (
        await conn.execute(
            "select r.id, r.object_id, r.location_id, r.object_kind, r.lease_id, "
            "       r.category, r.priority, r.title, r.description, r.revision, r.state, "
            "       r.approved_limit_minor, r.currency, r.contractor_id, r.recorded_by, "
            "       r.recorded_at, b.revision, b.company_id, b.contractor_id, rev.name "
            "from gba.property_maintenance_requests r "
            "join lateral ("
            "    select l.revision, l.company_id, l.contractor_id "
            "    from gba.property_maintenance_contractor_links l "
            "    where l.tenant_id = r.tenant_id and l.request_id = r.id "
            "    order by l.revision desc limit 1"
            ") b on true "
            "join lateral ("
            "    select v.name from gba.property_revisions v "
            "    where v.tenant_id = r.tenant_id and v.object_id = r.object_id "
            "    order by v.revision desc limit 1"
            ") rev on true "
            "where r.tenant_id = %s and r.id = %s",
            (business, request_id),
        )
    ).fetchone()
    if (
        row is None
        or row[17] != delegation.servicer_business_id
        or row[18] != row[13]
        or (location_id is not None and row[2] != location_id)
    ):
        raise PermissionDeniedError("Contractor grant does not authorize this maintenance request")
    req = MaintenanceRequestView(
        request_id=row[0],
        object_id=row[1],
        location_id=row[2],
        object_kind=row[3],
        lease_id=row[4],
        category=row[5],
        priority=row[6],
        title=row[7],
        description=row[8],
        revision=row[9],
        state=row[10],
        approved_limit_minor=row[11],
        currency=row[12],
        contractor_id=row[13],
        recorded_by=row[14],
        recorded_at=row[15],
    )
    return req, int(row[16]), str(row[19])


async def get_contractor_work(
    conn: RuntimeConnection,
    business: UUID,
    request_id: UUID,
    delegation: DelegationScope,
    *,
    location_id: UUID | None,
) -> ContractorWorkOrderView:
    req, binding_rev, object_name = await _require_contractor_binding(
        conn, business, request_id, delegation, location_id
    )
    updates = await _load_contractor_updates(conn, business, request_id)
    return ContractorWorkOrderView(
        request_id=req.request_id,
        object_id=req.object_id,
        object_name=object_name,
        object_kind=req.object_kind,
        location_id=req.location_id,
        category=req.category,
        priority=req.priority,
        title=req.title,
        description=req.description,
        state=req.state,
        revision=req.revision,
        binding_revision=binding_rev,
        contractor_company_id=delegation.servicer_business_id,
        updates=updates,
    )


async def record_contractor_update(
    conn: RuntimeConnection,
    business: UUID,
    request_id: UUID,
    delegation: DelegationScope,
    *,
    location_id: UUID | None,
    user_id: UUID,
    actor: str,
    key: str,
    body: ContractorUpdateInput,
) -> ContractorUpdateView:
    req, binding_rev, _ = await _require_contractor_binding(
        conn, business, request_id, delegation, location_id
    )
    scope = IdempotencyScope(business, actor, "property.maintenance.contractor_update", key)
    fingerprint = commands.fingerprint(
        {
            "request_id": str(request_id),
            "grant_id": str(delegation.grant_id),
            **body.model_dump(mode="json"),
        }
    )
    receipt = await commands.claim(conn, scope, fingerprint, _ContractorUpdateReceipt)
    if receipt is not None:
        updates = await _load_contractor_updates(conn, business, receipt.request_id)
        for item in updates:
            if item.number == receipt.number:
                return item
        raise NotFoundError("Contractor update not found")

    if not modules.MODULES_BY_ID[PROPERTY_MODULE].enableable:
        raise PropertyNotReadyError("The property module is not ready", module_id=PROPERTY_MODULE)
    await require_module(conn, business, PROPERTY_MODULE)

    await conn.execute("select gba.lock_property_object(%s, %s)", (business, req.object_id))
    req, binding_rev, _ = await _require_contractor_binding(
        conn, business, request_id, delegation, location_id
    )
    seq_row = await (
        await conn.execute(
            "select coalesce(max(number), 0) + 1 "
            "from gba.property_maintenance_contractor_updates "
            "where tenant_id = %s and request_id = %s",
            (business, request_id),
        )
    ).fetchone()
    number = int(seq_row[0]) if seq_row is not None else 1

    try:
        async with module_writes(PROPERTY_MODULE):
            await conn.execute(
                "insert into gba.property_maintenance_contractor_updates "
                "(tenant_id, request_id, number, kind, note, company_id, grant_id, "
                " binding_revision, recorded_by) "
                "values (%s,%s,%s,%s,%s,%s,%s,%s,%s)",
                (
                    business,
                    request_id,
                    number,
                    body.kind,
                    body.note,
                    delegation.servicer_business_id,
                    delegation.grant_id,
                    binding_rev,
                    user_id,
                ),
            )
    except errors.CheckViolation as exc:
        match exc.diag.constraint_name:
            case "property_maintenance_contractor_updates_state":
                raise MaintenanceStateError(
                    "Only an assigned maintenance request accepts contractor updates"
                ) from exc
            case "property_maintenance_contractor_updates_scope":
                raise PermissionDeniedError(
                    "Contractor grant does not authorize this maintenance request"
                ) from exc
        raise

    await commands.audit(
        conn,
        business,
        actor,
        "property.maintenance_contractor_update_recorded",
        "property_maintenance_request",
        str(request_id),
        {
            "number": number,
            "kind": body.kind,
            "grant_id": str(delegation.grant_id),
            "company_id": str(delegation.servicer_business_id),
            "binding_revision": binding_rev,
        },
    )
    await commands.complete(
        conn, scope, _ContractorUpdateReceipt(request_id=request_id, number=number)
    )
    updates = await _load_contractor_updates(conn, business, request_id)
    for item in updates:
        if item.number == number:
            return item
    raise NotFoundError("Contractor update not found")
